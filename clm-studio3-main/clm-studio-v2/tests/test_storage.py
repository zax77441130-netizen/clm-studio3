import json
import multiprocessing
import os
import time
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault('ADMIN_TOKEN', 'test-token')

from backend.app import storage


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    monkeypatch.setattr(storage, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(storage, 'SITE_FILE', tmp_path / 'site.json')
    monkeypatch.setattr(storage, 'UPLOADS_DIR', uploads)
    monkeypatch.setattr(storage, 'LOCK_FILE', tmp_path / '.site.lock')
    monkeypatch.setattr(storage, 'BACKUP_DIR', tmp_path / '.site-backups')
    monkeypatch.setattr(storage, 'RESTORE_BACKUP_DIR', tmp_path / '.restore-backups')
    storage.initialize_data()
    return tmp_path


def _snapshot_site_and_uploads():
    uploads = {
        item.relative_to(storage.UPLOADS_DIR).as_posix(): item.read_bytes()
        for item in storage.UPLOADS_DIR.rglob('*')
        if item.is_file()
    }
    return storage.SITE_FILE.read_bytes(), uploads


def _write_restore_archive(path, entries):
    with zipfile.ZipFile(path, 'w') as output:
        output.writestr('site.json', storage.SITE_FILE.read_bytes())
        for name, content in entries:
            output.writestr(name, content)


def test_repeated_reads_do_not_modify_file(data_dir):
    before = storage.SITE_FILE.read_bytes()
    before_mtime = storage.SITE_FILE.stat().st_mtime_ns
    for _ in range(5):
        storage.read_data()
    assert storage.SITE_FILE.read_bytes() == before
    assert storage.SITE_FILE.stat().st_mtime_ns == before_mtime


@pytest.mark.parametrize('content,exception', [
    (b'{broken', storage.DataCorruptError),
    (json.dumps({'site': []}).encode(), storage.DataValidationError),
])
def test_invalid_existing_data_is_preserved(data_dir, content, exception):
    storage.SITE_FILE.write_bytes(content)
    with pytest.raises(exception):
        storage.read_data()
    assert storage.SITE_FILE.read_bytes() == content


def test_missing_file_is_not_initialized_implicitly(data_dir):
    storage.SITE_FILE.unlink()
    with pytest.raises(storage.DataMissingError):
        storage.read_data()
    assert not storage.SITE_FILE.exists()


def test_stale_version_is_rejected_without_changes(data_dir):
    data, version = storage.read_data_with_version()
    data['site']['zh']['studio_name'] = 'first'
    new_version = storage.write_data(data, version)
    current = storage.SITE_FILE.read_bytes()
    data['site']['zh']['studio_name'] = 'stale'
    with pytest.raises(storage.VersionConflictError):
        storage.write_data(data, version)
    assert storage.SITE_FILE.read_bytes() == current
    assert new_version == storage.data_version(current)


def test_backup_failure_preserves_original(data_dir, monkeypatch):
    data, version = storage.read_data_with_version()
    original = storage.SITE_FILE.read_bytes()
    data['site']['zh']['studio_name'] = 'changed'
    monkeypatch.setattr(storage, '_backup_site_locked', lambda _: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        storage.write_data(data, version)
    assert storage.SITE_FILE.read_bytes() == original


def test_replace_failure_preserves_original(data_dir, monkeypatch):
    data, version = storage.read_data_with_version()
    original = storage.SITE_FILE.read_bytes()
    data['site']['zh']['studio_name'] = 'changed'
    monkeypatch.setattr(storage.os, 'replace', lambda *_: (_ for _ in ()).throw(OSError('replace failed')))
    with pytest.raises(storage.StorageError):
        storage.write_data(data, version)
    assert storage.SITE_FILE.read_bytes() == original


def test_post_replace_sync_failure_reports_that_data_changed(data_dir, monkeypatch):
    data, version = storage.read_data_with_version()
    data['site']['zh']['studio_name'] = 'replacement completed'
    original_replace = storage.os.replace
    original_fsync_directory = storage._fsync_directory
    site_was_replaced = False

    def tracked_replace(source, destination):
        nonlocal site_was_replaced
        original_replace(source, destination)
        if Path(destination) == storage.SITE_FILE:
            site_was_replaced = True

    def fail_after_site_replace(path):
        if site_was_replaced and Path(path) == storage.DATA_DIR:
            raise OSError('directory fsync failed')
        original_fsync_directory(path)

    monkeypatch.setattr(storage.os, 'replace', tracked_replace)
    monkeypatch.setattr(storage, '_fsync_directory', fail_after_site_replace)
    with pytest.raises(storage.PostReplaceSyncError, match='was replaced'):
        storage.write_data(data, version)
    assert json.loads(storage.SITE_FILE.read_text(encoding='utf-8'))['site']['zh']['studio_name'] == 'replacement completed'


def _concurrent_writer(data_dir_string, worker_id):
    root = Path(data_dir_string)
    storage.DATA_DIR = root
    storage.SITE_FILE = root / 'site.json'
    storage.UPLOADS_DIR = root / 'uploads'
    storage.LOCK_FILE = root / '.site.lock'
    storage.BACKUP_DIR = root / '.site-backups'
    storage.RESTORE_BACKUP_DIR = root / '.restore-backups'
    for sequence in range(15):
        for _ in range(50):
            data, version = storage.read_data_with_version()
            data['site']['zh']['studio_name'] = f'{worker_id}-{sequence}'
            try:
                storage.write_data(data, version)
                break
            except storage.VersionConflictError:
                time.sleep(0.001)


def test_multiprocess_writes_remain_complete_json(data_dir):
    context = multiprocessing.get_context('fork')
    processes = [context.Process(target=_concurrent_writer, args=(str(data_dir), index)) for index in range(4)]
    for process in processes:
        process.start()
    while any(process.is_alive() for process in processes):
        json.loads(storage.SITE_FILE.read_text(encoding='utf-8'))
    for process in processes:
        process.join()
        assert process.exitcode == 0
    storage.read_data()
    assert not list(data_dir.glob('.site-*.tmp'))


def test_full_backup_restores_site_and_uploads(data_dir):
    original_data, original_version = storage.read_data_with_version()
    (storage.UPLOADS_DIR / 'image.jpg').write_bytes(b'image-one')
    archive = data_dir / 'download.zip'
    storage.create_full_backup(archive)

    changed = json.loads(json.dumps(original_data))
    changed['site']['zh']['studio_name'] = 'changed'
    storage.write_data(changed, original_version)
    (storage.UPLOADS_DIR / 'image.jpg').write_bytes(b'image-two')

    restored_version = storage.restore_full_backup(archive)
    restored, current_version = storage.read_data_with_version()
    assert restored['site']['zh']['studio_name'] == original_data['site']['zh']['studio_name']
    assert (storage.UPLOADS_DIR / 'image.jpg').read_bytes() == b'image-one'
    assert restored_version == current_version


def test_restore_first_upload_rename_failure_preserves_every_byte(data_dir, monkeypatch):
    (storage.UPLOADS_DIR / 'first.bin').write_bytes(b'\x00old-first\xff')
    nested = storage.UPLOADS_DIR / 'nested'
    nested.mkdir()
    (nested / 'second.bin').write_bytes(b'old-second')
    archive = data_dir / 'restore.zip'
    _write_restore_archive(archive, [('uploads/new.bin', b'new')])
    before = _snapshot_site_and_uploads()
    original_replace = storage.os.replace

    def fail_first_upload_rename(source, destination):
        if Path(source) == storage.UPLOADS_DIR:
            raise OSError('injected first upload rename failure')
        return original_replace(source, destination)

    monkeypatch.setattr(storage.os, 'replace', fail_first_upload_rename)
    with pytest.raises(OSError, match='first upload rename failure'):
        storage.restore_full_backup(archive)
    assert _snapshot_site_and_uploads() == before


def test_restore_fsyncs_parent_after_each_persistent_switch(data_dir, monkeypatch):
    (storage.UPLOADS_DIR / 'old.bin').write_bytes(b'old')
    archive = data_dir / 'restore-order.zip'
    _write_restore_archive(archive, [('uploads/new.bin', b'new')])
    original_replace = storage.os.replace
    original_rmtree = storage.shutil.rmtree
    original_fsync_directory = storage._fsync_directory
    events = []

    def tracked_replace(source, destination):
        original_replace(source, destination)
        events.append(('replace', Path(source), Path(destination)))

    def tracked_rmtree(path, *args, **kwargs):
        original_rmtree(path, *args, **kwargs)
        events.append(('rmtree', Path(path)))

    def tracked_fsync(path):
        original_fsync_directory(path)
        events.append(('fsync', Path(path)))

    monkeypatch.setattr(storage.os, 'replace', tracked_replace)
    monkeypatch.setattr(storage.shutil, 'rmtree', tracked_rmtree)
    monkeypatch.setattr(storage, '_fsync_directory', tracked_fsync)
    storage.restore_full_backup(archive)

    persistent_changes = [
        index for index, event in enumerate(events)
        if (
            event[0] == 'replace'
            and (event[1] == storage.UPLOADS_DIR or event[2] in {storage.UPLOADS_DIR, storage.SITE_FILE})
        ) or (
            event[0] == 'rmtree'
            and event[1].parent == storage.DATA_DIR
            and event[1].name.startswith('.uploads-old-')
        )
    ]
    assert len(persistent_changes) == 4
    for index in persistent_changes:
        assert events[index + 1] == ('fsync', storage.DATA_DIR)


@pytest.mark.parametrize('unsafe_name', ['../escape.txt', '/absolute.txt', 'uploads/../../escape.txt'])
def test_restore_rejects_unsafe_archive_paths(data_dir, unsafe_name):
    archive = data_dir / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('site.json', storage.SITE_FILE.read_bytes())
        output.writestr(unsafe_name, b'unsafe')
    before = storage.SITE_FILE.read_bytes()
    with pytest.raises(storage.DataValidationError):
        storage.restore_full_backup(archive)
    assert storage.SITE_FILE.read_bytes() == before


@pytest.mark.parametrize('entries', [
    [('uploads/a.png', b'one'), ('uploads/./a.png', b'two')],
    [('uploads/item', b'file'), ('uploads/item/child.png', b'child')],
    [('uploads/item/child.png', b'child'), ('uploads/item', b'file')],
])
def test_restore_rejects_normalized_duplicates_and_file_directory_conflicts(data_dir, entries):
    (storage.UPLOADS_DIR / 'existing.bin').write_bytes(b'keep exactly')
    before = _snapshot_site_and_uploads()
    archive = data_dir / 'conflict.zip'
    _write_restore_archive(archive, entries)
    with pytest.raises(storage.DataValidationError):
        storage.restore_full_backup(archive)
    assert _snapshot_site_and_uploads() == before


def test_restart_reads_persisted_content_and_media(data_dir):
    data, version = storage.read_data_with_version()
    data['site']['zh']['studio_name'] = 'persisted'
    storage.write_data(data, version)
    (storage.UPLOADS_DIR / 'persisted.png').write_bytes(b'png')
    loaded, _ = storage.read_data_with_version()
    assert loaded['site']['zh']['studio_name'] == 'persisted'
    assert (storage.UPLOADS_DIR / 'persisted.png').read_bytes() == b'png'
