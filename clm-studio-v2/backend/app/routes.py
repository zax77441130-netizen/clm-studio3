from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Request, Response
from .config import settings, UPLOADS_DIR
from .storage import read_data, write_data, ensure_data
from .schemas import SitePayload
from .security import enforce_rate_limit, assert_not_locked, record_failed_verification, get_remaining_attempts, clear_failed_verification, create_admin_session, require_admin_session, clear_admin_session

router = APIRouter()
ensure_data()

def check_admin(token: str | None):
    if token != settings.admin_token:
        raise HTTPException(status_code=401, detail='invalid admin token')

@router.get('/health')
def health():
    return {'ok': True, 'service': settings.app_name}

@router.get('/site')
def site():
    return read_data()

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
    create_admin_session(request, response)
    return {'ok': True, 'remaining_attempts': get_remaining_attempts(request)}

@router.post('/admin/logout')
def admin_logout(request: Request, response: Response):
    clear_admin_session(request, response)
    return {'ok': True}

@router.get('/admin/verify')
def verify_admin(request: Request):
    require_admin_session(request)
    return {'ok': True}

@router.post('/admin/site')
def save_site(request: Request, payload: SitePayload):
    enforce_rate_limit(request, 'admin_site')
    require_admin_session(request)
    write_data(payload.model_dump())
    return {'ok': True}

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm'}
ALLOWED_CONTENT_TYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif', 'video/mp4', 'video/webm'}
MAX_UPLOAD_SIZE = 15 * 1024 * 1024

@router.post('/admin/upload')
def upload(request: Request, file: UploadFile = File(...)):
    enforce_rate_limit(request, 'upload')
    require_admin_session(request)
    ext = Path(file.filename or '').suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail='file type not allowed')
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail='content type not allowed')
    content = file.file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail='file too large')
    name = f'{uuid4().hex}{ext}'
    target = UPLOADS_DIR / name
    with target.open('wb') as f:
        f.write(content)
    return {'ok': True, 'path': f'/uploads/{name}'}
