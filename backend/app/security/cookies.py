"""会话 cookie 与 CSRF。

- access_token：httpOnly，Path=/api，短期。
- refresh_token：httpOnly，Path=/api/v1/auth，只在刷新/登出时发送。
- csrf_token：前端可读（非 httpOnly），写操作须在 X-CSRF-Token 头里回传同值（双提交）。
三者都是 Secure + SameSite=Strict。
"""

from __future__ import annotations

import hmac
import secrets

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
        CSRF_COOKIE, secrets.token_urlsafe(24), max_age=s.refresh_token_ttl_s, httponly=False, path="/", **common
    )
    resp.headers["Cache-Control"] = "no-store"


def clear_session(resp: Response, s: Settings) -> None:
    for name, path, http_only in (
        (ACCESS_COOKIE, ACCESS_PATH, True),
        (REFRESH_COOKIE, REFRESH_PATH, True),
        (CSRF_COOKIE, "/", False),
    ):
        resp.delete_cookie(name, path=path, secure=s.cookie_secure, httponly=http_only, samesite="strict")


def csrf_ok(request: Request) -> bool:
    """用 cookie 认证的写请求必须带匹配的 CSRF 头；用 Bearer 头认证的请求不受 CSRF 影响。"""
    if request.method not in UNSAFE or request.url.path in CSRF_EXEMPT:
        return True
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return True
    if ACCESS_COOKIE not in request.cookies and REFRESH_COOKIE not in request.cookies:
        return True  # 无会话，后续鉴权会返回 401
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    return bool(cookie) and hmac.compare_digest(cookie, header)
