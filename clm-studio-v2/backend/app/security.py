from time import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request, Response

RATE_WINDOWS = {
    'admin_verify': (8, 300),
    'admin_site': (20, 300),
    'upload': (10, 300),
}
LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 900
SESSION_TTL_SECONDS = 8 * 60 * 60

_hits: dict[str, deque] = defaultdict(deque)
_failed_verifications: dict[str, deque] = defaultdict(deque)
_lockouts: dict[str, float] = {}
_admin_sessions: dict[str, float] = {}


def _client_host(request: Request) -> str:
    return request.client.host if request.client else 'unknown'


def _client_key(request: Request, scope: str) -> str:
    return f'{scope}:{_client_host(request)}'


def _prune(queue: deque, window: int, now: float):
    while queue and now - queue[0] > window:
        queue.popleft()


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


def create_admin_session(request: Request, response: Response):
    now = time()
    host = _client_host(request)
    expires_at = now + SESSION_TTL_SECONDS
    _admin_sessions[host] = expires_at
    response.set_cookie('clm_admin_session', host, max_age=SESSION_TTL_SECONDS, httponly=True, samesite='Strict', secure=False)


def require_admin_session(request: Request):
    now = time()
    cookie_host = request.cookies.get('clm_admin_session')
    real_host = _client_host(request)
    if not cookie_host or cookie_host != real_host:
        raise HTTPException(status_code=401, detail='admin session required')
    expires_at = _admin_sessions.get(real_host)
    if not expires_at or expires_at < now:
        _admin_sessions.pop(real_host, None)
        raise HTTPException(status_code=401, detail='admin session expired')


def clear_admin_session(request: Request, response: Response):
    host = _client_host(request)
    _admin_sessions.pop(host, None)
    response.delete_cookie('clm_admin_session')
