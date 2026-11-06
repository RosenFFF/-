"""会话 cookie 与 CSRF。

- access_token：httpOnly，Path=/api，短期。
- refresh_token：httpOnly，Path=/api/v1/auth，只在刷新/登出时发送。
- csrf_token：前端可读（非 httpOnly），写操作须在 X-CSRF-Token 头里回传同值（双提交）。
三者都是 Secure + SameSite=Strict。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import Request, Response

from app.core.config import Settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
ACCESS_PATH = "/api"
REFRESH_PATH = "/api/v1/auth"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT = {"/api/v1/auth/login"}


def set_session(resp: Response, s: Settings, *, access: str, refresh: str) -> None:
    common = {"secure": s.cookie_secure, "samesite": "strict"}
    resp.set_cookie(ACCESS_COOKIE, access, max_age=s.access_token_ttl_s, httponly=True, path=ACCESS_PATH, **common)
    resp.set_cookie(REFRESH_COOKIE, refresh, max_age=s.refresh_token_ttl_s, httponly=True, path=REFRESH_PATH, **common)
    resp.set_cookie(
        CSRF_COOKIE, issue_csrf(s, access, refresh), max_age=s.refresh_token_ttl_s, httponly=False, path="/", **common
    )
    resp.headers["Cache-Control"] = "no-store"


def clear_session(resp: Response, s: Settings) -> None:
    for name, path, http_only in (
        (ACCESS_COOKIE, ACCESS_PATH, True),
        (REFRESH_COOKIE, REFRESH_PATH, True),
        (CSRF_COOKIE, "/", False),
    ):
        resp.delete_cookie(name, path=path, secure=s.cookie_secure, httponly=http_only, samesite="strict")


def _signature(s: Settings, nonce: str, kind: str, token: str) -> str:
    return hmac.new(s.jwt_secret.encode(), f"csrf-v1:{nonce}:{kind}:{token}".encode(), hashlib.sha256).hexdigest()


def issue_csrf(s: Settings, access: str, refresh: str) -> str:
    nonce = secrets.token_urlsafe(24)
    return f"{nonce}.{_signature(s, nonce, 'access', access)}.{_signature(s, nonce, 'refresh', refresh)}"


def _origin(value: str, *, referer: bool = False) -> str | None:
    try:
        u = urlsplit(value)
        if u.scheme not in {"https", "http"} or not u.hostname or u.username or u.password:
            return None
        if not referer and (u.path or u.query or u.fragment):
            return None
        port = u.port
        host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
        default = 443 if u.scheme == "https" else 80
        return f"{u.scheme}://{host}" + (f":{port}" if port and port != default else "")
    except ValueError:
        return None


def csrf_ok(request: Request) -> bool:
    """签名双提交绑定当前 access/refresh；refresh 续期可在 access 已过期后校验。

    Origin 优先，只有缺失时才回退 Referer；不能用攻击者的 Referer 覆盖坏 Origin。
    携带会话 Cookie 时不得用伪造 Bearer 头绕过此检查。
    """
    if request.method not in UNSAFE:
        return True
    s = request.app.state.settings
    has_cookie = ACCESS_COOKIE in request.cookies or REFRESH_COOKIE in request.cookies
    if not has_cookie and request.url.path not in CSRF_EXEMPT:
        return True  # 无 Cookie 的脚本认证不受浏览器 CSRF 影响
    source = request.headers.get("origin")
    if source is None:
        source = request.headers.get("referer", "")
    allowed = {_origin(v) for v in s.cors_origins}
    origin = _origin(source, referer=request.headers.get("origin") is None)
    if origin is None or origin not in allowed:
        return False
    if request.url.path in CSRF_EXEMPT:
        return True  # 登录无会话 CSRF，但仍校验来源，防登录 CSRF
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if (
        not cookie
        or len(cookie) > 256
        or len(header) > 256
        or not cookie.isascii()
        or not header.isascii()
        or not hmac.compare_digest(cookie, header)
    ):
        return False
    parts = cookie.split(".")
    if len(parts) != 3:
        return False
    nonce, access_sig, refresh_sig = parts
    access = request.cookies.get(ACCESS_COOKIE)
    refresh = request.cookies.get(REFRESH_COOKIE)
    if access and not hmac.compare_digest(access_sig, _signature(s, nonce, "access", access)):
        return False
    if refresh and not hmac.compare_digest(refresh_sig, _signature(s, nonce, "refresh", refresh)):
        return False
    return bool(access or refresh)
