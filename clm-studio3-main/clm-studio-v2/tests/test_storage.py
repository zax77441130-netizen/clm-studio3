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


def test_restart_reads_persisted_content_and_media(data_dir):
    data, version = storage.read_data_with_version()
    data['site']['zh']['studio_name'] = 'persisted'
    storage.write_data(data, version)
    (storage.UPLOADS_DIR / 'persisted.png').write_bytes(b'png')
    loaded, _ = storage.read_data_with_version()
    assert loaded['site']['zh']['studio_name'] == 'persisted'
    assert (storage.UPLOADS_DIR / 'persisted.png').read_bytes() == b'png'
