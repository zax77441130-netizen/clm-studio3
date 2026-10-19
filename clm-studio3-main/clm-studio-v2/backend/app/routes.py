from io import BytesIO
from pathlib import Path
from uuid import uuid4
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from urllib.parse import urlparse
from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Request, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, ValidationError
from PIL import Image, ImageSequence
from .config import settings, UPLOADS_DIR
from .storage import (
    DataCorruptError,
    DataMissingError,
    DataValidationError,
    StorageError,
    VersionConflictError,
    create_full_backup,
    read_data_with_version,
    restore_full_backup,
    with_storage_lock,
    write_data,
)
from .schemas import SitePayload
from .security import (
    enforce_rate_limit,
    assert_not_locked,
    record_failed_verification,
    get_remaining_attempts,
    clear_failed_verification,
    create_admin_session,
    require_admin_session,
    require_csrf,
    clear_admin_session,
)

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_ENABLED = True
except Exception:
    HEIF_ENABLED = False

router = APIRouter()
MAX_BACKUP_UPLOAD_SIZE = 1024 * 1024 * 1024


class TranslatePayload(BaseModel):
    text: str = ''


def check_admin(token: str | None):
    if token != settings.admin_token:
        raise HTTPException(status_code=401, detail='invalid admin token')


def _sanitize_error_message(_: Exception | None = None, fallback: str = 'request failed') -> str:
    return fallback


def _validate_embed_code(embed_code: str) -> str:
    code = (embed_code or '').strip()
    if not code:
        return ''
    lowered = code.lower()
    blocked = ['<script', 'onerror=', 'onclick=', 'onload=', 'javascript:', 'data:']
    if any(token in lowered for token in blocked):
        raise HTTPException(status_code=400, detail='invalid embed code')
    iframe_match = re.fullmatch(r'\s*<iframe\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*></iframe>\s*', code, re.IGNORECASE)
    if not iframe_match:
        raise HTTPException(status_code=400, detail='invalid embed code')
    src = iframe_match.group(1).strip()
    parsed = urlparse(src)
    if parsed.scheme != 'https':
        raise HTTPException(status_code=400, detail='invalid embed code')
    allowed_hosts = {'www.youtube.com', 'youtube.com', 'player.vimeo.com', 'www.google.com', 'drive.google.com'}
    if parsed.netloc not in allowed_hosts:
        raise HTTPException(status_code=400, detail='invalid embed code')
    if parsed.netloc == 'www.google.com' and not parsed.path.startswith('/maps'):
        raise HTTPException(status_code=400, detail='invalid embed code')
    return code


def _is_allowed_contact_url(value: str) -> bool:
    text = (value or '').strip()
    return bool(re.match(r'^(https://|http://|mailto:|tel:)', text, re.IGNORECASE))


def _sanitize_site_payload_dict(payload: dict) -> dict:
    for item in payload.get('portfolio', []) or []:
        for media in item.get('media', []) or []:
            media['embed_code'] = _validate_embed_code(media.get('embed_code', ''))
    for contact in payload.get('contacts', []) or []:
        url = (contact.get('url') or '').strip()
        if not _is_allowed_contact_url(url):
            raise HTTPException(status_code=400, detail='invalid contact url')
        contact['url'] = url
    return payload


@router.get('/health')
def health():
    return {'ok': True, 'service': settings.app_name}


@router.get('/site')
def site():
    try:
        data, version = read_data_with_version()
    except (DataMissingError, DataCorruptError, DataValidationError, StorageError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    data['_version'] = version
    return data


@router.get('/admin/login-status')
def admin_login_status(request: Request):
    assert_not_locked(request)
    return {'ok': True, 'remaining_attempts': get_remaining_attempts(request)}


@router.post('/admin/login')
def admin_login(request: Request, response: Response, x_admin_token: str | None = Header(default=None)):
    enforce_rate_limit(request, 'admin_verify')
    assert_not_locked(request)
    try:
        check_admin(x_admin_token)
    except HTTPException:
        remaining = record_failed_verification(request)
        raise HTTPException(status_code=401, detail=f'密碼錯誤，剩餘 {remaining} 次')
    clear_failed_verification(request)
    session = create_admin_session(response)
    return {'ok': True, 'remaining_attempts': get_remaining_attempts(request), 'csrf_token': session['csrf_token']}


@router.post('/admin/logout')
def admin_logout(request: Request, response: Response):
    require_admin_session(request)
    require_csrf(request)
    clear_admin_session(request, response)
    return {'ok': True}


@router.get('/admin/verify')
def verify_admin(request: Request):
    _, payload = require_admin_session(request)
    return {'ok': True, 'csrf_token': payload.get('csrf_token')}


@router.post('/admin/site')
async def save_site(request: Request):
    enforce_rate_limit(request, 'admin_site')
    require_admin_session(request)
    require_csrf(request)
    try:
        raw_payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='invalid json payload')
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=422, detail='payload must be a JSON object')
    expected_version = raw_payload.pop('_version', None)
    try:
        payload = SitePayload.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    payload_dict = _sanitize_site_payload_dict(payload.model_dump(by_alias=True))
    try:
        version = write_data(payload_dict, expected_version)
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (DataMissingError, DataCorruptError, DataValidationError, StorageError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {'ok': True, 'version': version}


@router.get('/admin/backup')
def download_backup(request: Request):
    enforce_rate_limit(request, 'admin_site')
    require_admin_session(request)
    fd, name = tempfile.mkstemp(prefix='clm-studio-backup-', suffix='.zip')
    os.close(fd)
    target = Path(name)
    try:
        create_full_backup(target)
    except (DataMissingError, DataCorruptError, DataValidationError, StorageError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(exc))
    return FileResponse(
        target,
        media_type='application/zip',
        filename='clm-studio-backup.zip',
        background=BackgroundTask(target.unlink, missing_ok=True),
    )


@router.post('/admin/restore')
def restore_backup(request: Request, file: UploadFile = File(...)):
    enforce_rate_limit(request, 'admin_site')
    require_admin_session(request)
    require_csrf(request)
    fd, name = tempfile.mkstemp(prefix='clm-studio-restore-', suffix='.zip')
    source = Path(name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            total = 0
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BACKUP_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail='backup file exceeds 1 GiB limit')
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        version = restore_full_backup(source)
    except (DataValidationError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (DataMissingError, DataCorruptError, StorageError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        source.unlink(missing_ok=True)
    return {'ok': True, 'version': version}


ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm', '.mov', '.heic', '.heif'}
ALLOWED_CONTENT_TYPES = {
    'image/png', 'image/jpeg', 'image/webp', 'image/gif',
    'video/mp4', 'video/webm', 'video/quicktime',
    'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence',
    'application/octet-stream'
}
MAX_UPLOAD_SIZE = 30 * 1024 * 1024
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.heic', '.heif'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov'}
ALLOWED_VIDEO_MIME = {'video/mp4', 'video/webm', 'video/quicktime', 'application/octet-stream'}
LOSSLESS_IMAGE_EXTENSIONS = {'.png', '.webp', '.gif'}


def save_image_as_web_friendly(content: bytes, original_ext: str) -> tuple[str, bool]:
    image = Image.open(BytesIO(content))
    image.verify()
    image = Image.open(BytesIO(content))
    ext = original_ext.lower()

    if ext == '.gif':
        frames = [frame.copy() for frame in ImageSequence.Iterator(image)]
        if not frames:
            raise ValueError('empty gif')
        name = f'{uuid4().hex}.gif'
        target = UPLOADS_DIR / name
        first, rest = frames[0], frames[1:]
        save_kwargs = {
            'format': 'GIF',
            'save_all': True,
            'append_images': rest,
            'loop': image.info.get('loop', 0),
            'duration': image.info.get('duration', 100),
            'disposal': 2,
        }
        if 'transparency' in image.info:
            save_kwargs['transparency'] = image.info['transparency']
        first.save(target, **save_kwargs)
        return f'/uploads/{name}', False

    if ext in LOSSLESS_IMAGE_EXTENSIONS:
        name = f'{uuid4().hex}{ext}'
        target = UPLOADS_DIR / name
        target.write_bytes(content)
        return f'/uploads/{name}', False

    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGB')
    elif image.mode == 'RGBA':
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel('A'))
        image = background
    name = f'{uuid4().hex}.jpg'
    target = UPLOADS_DIR / name
    image.save(target, format='JPEG', quality=92, optimize=True)
    return f'/uploads/{name}', ext not in {'.jpg', '.jpeg'}


def convert_mov_to_mp4(content: bytes) -> str:
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        raise HTTPException(status_code=400, detail='MOV 影片需要先轉成 MP4，或在伺服器安裝 ffmpeg 後再上傳')

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        source_path = temp_dir_path / 'source.mov'
        output_path = temp_dir_path / 'output.mp4'
        source_path.write_bytes(content)
        result = subprocess.run(
            [
                ffmpeg_path,
                '-y',
                '-i', str(source_path),
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-movflags', '+faststart',
                str(output_path)
            ],
            capture_output=True,
            text=True
        )
        if result.returncode != 0 or not output_path.exists():
            raise HTTPException(status_code=400, detail='MOV 轉 MP4 失敗，請先自行轉成標準 MP4（H.264 / AAC）再上傳')
        name = f'{uuid4().hex}.mp4'
        target = UPLOADS_DIR / name
        target.write_bytes(output_path.read_bytes())
        return f'/uploads/{name}'


@router.post('/admin/translate-service')
def translate_service(request: Request, payload: TranslatePayload):
    enforce_rate_limit(request, 'admin_site')
    require_admin_session(request)
    require_csrf(request)
    source = (payload.text or '').strip()
    if not source:
        return {'ok': True, 'text': ''}

    replacements = [
        ('與', ' and '), ('及', ' and '), ('、', ', '), ('／', ' / '), ('，', ', '),
        ('網站', 'website'), ('系統', 'system'), ('開發', 'development'), ('建置', 'setup'),
        ('整合', 'integration'), ('自動化', 'automation'), ('流程', 'workflow'), ('品牌', 'brand'),
        ('企業', 'business'), ('客製化', 'custom'), ('智慧客服', 'smart support'), ('客服', 'support'),
        ('知識庫', 'knowledge base'), ('後台', 'admin'), ('資安', 'security'), ('檢查', 'review'),
        ('顧問', 'consulting'), ('研究', 'research'), ('服務', 'services'), ('案例', 'case study'),
        ('作品集', 'portfolio'), ('聯絡', 'contact'), ('免費諮詢', 'free consultation'),
        ('工作室', 'studio'), ('摘要', 'summary'), ('詳細介紹', 'detailed description'),
        ('技術標籤', 'tech stack'), ('導入', 'implementation'), ('串接', 'integration'),
        ('商業', 'business'), ('內容', 'content'), ('維護', 'maintenance'), ('操作', 'operations'),
        ('管理', 'management'), ('優化', 'optimization'), ('規劃', 'planning'), ('展示', 'showcase')
    ]
    translated = source
    for zh, en in replacements:
        translated = translated.replace(zh, en)
    translated = ' '.join(translated.split())
    return {'ok': True, 'text': translated}


@router.post('/admin/upload')
@with_storage_lock
def upload(request: Request, file: UploadFile = File(...)):
    enforce_rate_limit(request, 'upload')
    require_admin_session(request)
    require_csrf(request)
    ext = Path(file.filename or '').suffix.lower()
    if ext == '.svg':
        raise HTTPException(status_code=400, detail='SVG 上傳已禁止')
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail='不支援的檔案類型')
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail='檔案 MIME 類型不允許')
    content = file.file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail='檔案大小超過 30MB 限制')

    if ext in {'.heic', '.heif'}:
        if not HEIF_ENABLED:
            raise HTTPException(status_code=400, detail='伺服器尚未安裝 HEIC / HEIF 支援')
        path, converted = save_image_as_web_friendly(content, ext)
        return {'ok': True, 'path': path, 'converted': converted}

    if ext in IMAGE_EXTENSIONS:
        try:
            path, converted = save_image_as_web_friendly(content, ext)
            return {'ok': True, 'path': path, 'converted': converted}
        except Exception:
            raise HTTPException(status_code=400, detail='圖片檔案驗證失敗')

    if ext in VIDEO_EXTENSIONS:
        if file.content_type and file.content_type not in ALLOWED_VIDEO_MIME:
            raise HTTPException(status_code=400, detail='影片 MIME 類型不允許')
        if ext == '.mov':
            path = convert_mov_to_mp4(content)
            return {'ok': True, 'path': path, 'converted': True, 'source_ext': '.mov', 'target_ext': '.mp4'}
        name = f'{uuid4().hex}{ext}'
        target = UPLOADS_DIR / name
        with target.open('wb') as f:
            f.write(content)
        return {'ok': True, 'path': f'/uploads/{name}'}

    raise HTTPException(status_code=400, detail='不支援的檔案類型')
