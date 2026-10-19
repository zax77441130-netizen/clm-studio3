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
    # A self-contained fixture: no references to repository sample media.
    def clear_sample_media(value):
        if isinstance(value, dict):
            return {key: clear_sample_media(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clear_sample_media(item) for item in value]
        return '' if isinstance(value, str) and value.startswith('/uploads/') else value
    fixture_data = clear_sample_media(json.loads(storage.SITE_FILE.read_bytes()))
    storage.SITE_FILE.write_text(json.dumps(fixture_data), encoding='utf-8')
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


def _kill_during_restore(archive, point):
    import signal
    replace, write_state = storage.os.replace, storage._write_restore_state
    def checkpoint_replace(source, destination):
        replace(source, destination)
        hit = point == 'old-moved' and Path(source) == storage.UPLOADS_DIR
        hit |= point == 'new-installed' and Path(destination) == storage.UPLOADS_DIR
        hit |= point == 'site-installed' and Path(destination) == storage.SITE_FILE
        if hit: os.kill(os.getpid(), signal.SIGKILL)
    def checkpoint_state(journal, state):
        write_state(journal, state)
        if point == 'committed' and state['state'] == 'committed':
            os.kill(os.getpid(), signal.SIGKILL)
    storage.os.replace, storage._write_restore_state = checkpoint_replace, checkpoint_state
    storage.restore_full_backup(Path(archive))


def _run_killed_worker(function, args):
    process = multiprocessing.get_context('fork').Process(target=function, args=args)
    process.start(); process.join(timeout=15)
    if process.is_alive():
        process.kill(); process.join(); pytest.fail('worker timed out')
    assert process.exitcode == -9


@pytest.mark.parametrize('point', ['old-moved', 'new-installed', 'site-installed', 'committed'])
def test_sigkill_restore_recovery(data_dir, point):
    (storage.UPLOADS_DIR / 'old.bin').write_bytes(b'original media')
    before = _snapshot_site_and_uploads()
    changed = json.loads(before[0]); changed['site']['zh']['studio_name'] = 'RESTORED VERSION'
    archive = data_dir / 'crash.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('site.json', json.dumps(changed))
        output.writestr('uploads/new.bin', b'new media')
    _run_killed_worker(_kill_during_restore, (str(archive), point))
    loaded = storage.read_data()
    if point == 'committed':
        assert loaded['site']['zh']['studio_name'] == 'RESTORED VERSION'
        assert (storage.UPLOADS_DIR / 'new.bin').read_bytes() == b'new media'
        assert not (storage.UPLOADS_DIR / 'old.bin').exists()
    else:
        assert _snapshot_site_and_uploads() == before
    assert not (data_dir / '.restore-journal').exists()


def _kill_during_recovery():
    import signal
    replace = storage.os.replace
    def kill_after_media_recovery(source, destination):
        replace(source, destination)
        if Path(destination) == storage.UPLOADS_DIR: os.kill(os.getpid(), signal.SIGKILL)
    storage.os.replace = kill_after_media_recovery
    storage.recover_pending_restore()


def test_recovery_can_itself_be_interrupted(data_dir):
    (storage.UPLOADS_DIR / 'old.bin').write_bytes(b'original')
    before = _snapshot_site_and_uploads()
    archive = data_dir / 'crash-twice.zip'
    _write_restore_archive(archive, [('uploads/new.bin', b'new')])
    _run_killed_worker(_kill_during_restore, (str(archive), 'site-installed'))
    _run_killed_worker(_kill_during_recovery, ())
    storage.recover_pending_restore()
    assert _snapshot_site_and_uploads() == before


@pytest.mark.parametrize('root_name', ['uploads', 'site.json/'])
def test_restore_rejects_incorrect_root_entry_type(data_dir, root_name):
    before = _snapshot_site_and_uploads(); archive = data_dir / 'invalid-type.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        if root_name != 'site.json/': output.writestr('site.json', before[0])
        output.writestr(root_name, b'invalid type')
    with pytest.raises(storage.DataValidationError): storage.restore_full_backup(archive)
    assert _snapshot_site_and_uploads() == before


def test_incomplete_media_backup_preserves_current_state(data_dir):
    data, version = storage.read_data_with_version()
    data['site']['branding']['logo_path'] = '/uploads/required.png'
    (storage.UPLOADS_DIR / 'required.png').write_bytes(b'required media')
    storage.write_data(data, version)
    before = _snapshot_site_and_uploads(); archive = data_dir / 'missing-media.zip'
    _write_restore_archive(archive, [('uploads/unrelated.png', b'unrelated')])
    with pytest.raises(storage.DataValidationError, match='missing referenced media'):
        storage.restore_full_backup(archive)
    assert _snapshot_site_and_uploads() == before


def test_encoded_media_traversal_rejected(data_dir):
    data, _ = storage.read_data_with_version()
    data['site']['branding']['logo_path'] = '/uploads/%2e%2e/site.json'
    archive = data_dir / 'encoded.zip'
    with zipfile.ZipFile(archive, 'w') as output: output.writestr('site.json', json.dumps(data))
    before = _snapshot_site_and_uploads()
    with pytest.raises(storage.DataValidationError, match='unsafe media path'):
        storage.restore_full_backup(archive)
    assert _snapshot_site_and_uploads() == before


def test_write_invalid_payload_does_not_fill_template(data_dir):
    _, version = storage.read_data_with_version(); before = _snapshot_site_and_uploads()
    with pytest.raises(storage.DataValidationError): storage.write_data({}, version)
    assert _snapshot_site_and_uploads() == before


def test_invalid_journal_fails_closed(data_dir):
    before = _snapshot_site_and_uploads(); journal = data_dir / '.restore-journal'; journal.mkdir()
    (journal / 'state.json').write_text('{broken')
    with pytest.raises(storage.RestoreRollbackError): storage.read_data()
    assert _snapshot_site_and_uploads() == before
    assert (journal / 'state.json').read_text() == '{broken'


@pytest.fixture()
def api_client(data_dir, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app import routes, security
    monkeypatch.setattr(routes, 'UPLOADS_DIR', storage.UPLOADS_DIR)
    security._hits.clear(); security._admin_sessions.clear()
    app = FastAPI(); app.include_router(routes.router, prefix='/api')
    with TestClient(app) as client:
        yield client


def _admin_headers(client):
    result = client.post('/api/admin/login', headers={'X-Admin-Token': 'test-token'})
    assert result.status_code == 200
    return {'X-CSRF-Token': result.json()['csrf_token']}


def test_api_save_conflict_and_backup_restore(api_client, data_dir):
    import io
    headers = _admin_headers(api_client)
    before = storage.SITE_FILE.stat().st_mtime_ns
    first = api_client.get('/api/site'); assert first.status_code == 200
    assert storage.SITE_FILE.stat().st_mtime_ns == before
    payload = first.json(); payload['site']['zh']['studio_name'] = 'API verified'
    save = api_client.post('/api/admin/site', json=payload, headers=headers)
    assert save.status_code == 200
    assert api_client.post('/api/admin/site', json=payload, headers=headers).status_code == 409
    (storage.UPLOADS_DIR / 'test.bin').write_bytes(b'API backup media')
    backup = api_client.get('/api/admin/backup'); assert backup.status_code == 200
    with zipfile.ZipFile(io.BytesIO(backup.content)) as z:
        assert z.read('uploads/test.bin') == b'API backup media'
    restore = api_client.post('/api/admin/restore', files={'file': ('backup.zip', backup.content)}, headers=headers)
    assert restore.status_code == 200
    assert api_client.get('/api/site').json()['site']['zh']['studio_name'] == 'API verified'
    assert (storage.UPLOADS_DIR / 'test.bin').read_bytes() == b'API backup media'


def test_api_rejects_unauthorized_backup_and_restore(api_client):
    assert api_client.get('/api/admin/backup').status_code == 401
    assert api_client.post('/api/admin/restore', files={'file': ('test.zip', b'invalid')}).status_code == 401
    _admin_headers(api_client)
    assert api_client.post('/api/admin/restore', files={'file': ('test.zip', b'invalid')}).status_code == 403


def test_api_rejects_non_object_payload(api_client):
    headers = _admin_headers(api_client)
    assert api_client.post('/api/admin/site', json=[], headers=headers).status_code == 422


def test_api_corruption_fails_without_overwrite(api_client):
    storage.SITE_FILE.write_bytes(b'{broken')
    assert api_client.get('/api/site').status_code == 503
    assert storage.SITE_FILE.read_bytes() == b'{broken'


def test_fresh_application_start_recovers_interrupted_restore(data_dir):
    import subprocess
    import sys
    (storage.UPLOADS_DIR / 'old.bin').write_bytes(b'old startup media')
    before = _snapshot_site_and_uploads()
    archive = data_dir / 'startup.zip'
    changed = json.loads(before[0]); changed['site']['zh']['studio_name'] = 'interrupted'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('site.json', json.dumps(changed))
        output.writestr('uploads/new.bin', b'new startup media')
    _run_killed_worker(_kill_during_restore, (str(archive), 'site-installed'))
    code = "from backend.app.main import app; from backend.app.storage import read_data; print(read_data()['site']['zh']['studio_name'])"
    env = dict(os.environ, DATA_DIR=str(data_dir), ADMIN_TOKEN='test-token')
    result = subprocess.run([sys.executable, '-c', code], env=env, cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert _snapshot_site_and_uploads() == before
