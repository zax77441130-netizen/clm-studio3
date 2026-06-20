from time import time
from collections import defaultdict, deque
from secrets import token_urlsafe
from fastapi import HTTPException, Request, Response
from .config import settings

RATE_WINDOWS = {
    'admin_verify': (8, 300),
    'admin_site': (20, 300),
    'upload': (10, 300),
}
LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 900

_hits: dict[str, deque] = defaultdict(deque)
_failed_verifications: dict[str, deque] = defaultdict(deque)
_lockouts: dict[str, float] = {}
_admin_sessions: dict[str, dict] = {}


def _client_host(request: Request) -> str:
    return request.client.host if request.client else 'unknown'


def _client_key(request: Request, scope: str) -> str:
    return f'{scope}:{_client_host(request)}'


def _prune(queue: deque, window: int, now: float):
    while queue and now - queue[0] > window:
        queue.popleft()


def _prune_sessions(now: float | None = None):
    now = now or time()
    expired = [sid for sid, payload in _admin_sessions.items() if payload.get('expires_at', 0) < now]
    for sid in expired:
        _admin_sessions.pop(sid, None)


def enforce_rate_limit(request: Request, scope: str):
    max_hits, window = RATE_WINDOWS[scope]
    now = time()
    key = _client_key(request, scope)
    q = _hits[key]
    _prune(q, window, now)
    if len(q) >= max_hits:
        raise HTTPException(status_code=429, detail='too many requests')
    q.append(now)


def assert_not_locked(request: Request):
    now = time()
    host = _client_host(request)
    until = _lockouts.get(host)
    if until and until > now:
        retry_after = int(until - now)
        raise HTTPException(status_code=429, detail=f'too many failed attempts, retry in {retry_after}s')
    if until and until <= now:
        _lockouts.pop(host, None)
        _failed_verifications.pop(host, None)


def record_failed_verification(request: Request) -> int:
    now = time()
    host = _client_host(request)
    q = _failed_verifications[host]
    _prune(q, LOCKOUT_SECONDS, now)
    q.append(now)
    remaining = max(0, LOCKOUT_THRESHOLD - len(q))
    if len(q) >= LOCKOUT_THRESHOLD:
        _lockouts[host] = now + LOCKOUT_SECONDS
        raise HTTPException(status_code=429, detail='too many failed attempts, temporarily locked')
    return remaining


def get_remaining_attempts(request: Request) -> int:
    now = time()
    host = _client_host(request)
    q = _failed_verifications.get(host, deque())
    _prune(q, LOCKOUT_SECONDS, now)
    return max(0, LOCKOUT_THRESHOLD - len(q))


def clear_failed_verification(request: Request):
    host = _client_host(request)
    _failed_verifications.pop(host, None)
    _lockouts.pop(host, None)


def create_admin_session(response: Response):
    now = time()
    _prune_sessions(now)
    session_id = token_urlsafe(32)
    csrf_token = token_urlsafe(32)
    expires_at = now + settings.session_ttl_seconds
    _admin_sessions[session_id] = {
        'expires_at': expires_at,
        'csrf_token': csrf_token,
    }
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.is_production,
    )
    return {'session_id': session_id, 'csrf_token': csrf_token, 'expires_at': expires_at}


def _get_session(request: Request):
    now = time()
    _prune_sessions(now)
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(status_code=401, detail='admin session required')
    payload = _admin_sessions.get(session_id)
    if not payload:
        raise HTTPException(status_code=401, detail='admin session required')
    if payload.get('expires_at', 0) < now:
        _admin_sessions.pop(session_id, None)
        raise HTTPException(status_code=401, detail='admin session expired')
    return session_id, payload


def require_admin_session(request: Request):
    return _get_session(request)


def require_csrf(request: Request):
    _, payload = _get_session(request)
    token = request.headers.get(settings.csrf_header_name)
    if not token or token != payload.get('csrf_token'):
        raise HTTPException(status_code=403, detail='invalid csrf token')
    return payload


def clear_admin_session(request: Request, response: Response):
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        _admin_sessions.pop(session_id, None)
    response.delete_cookie(settings.session_cookie_name)
