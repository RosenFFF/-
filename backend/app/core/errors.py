"""统一错误：RFC 9457 problem+json，带稳定错误码和 request_id，不泄露堆栈。"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()


class AppError(Exception):
    def __init__(
        self, status: int, code: str, title: str, detail: str | None = None, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(title)
        self.status, self.code, self.title, self.detail, self.headers = status, code, title, detail, headers


def problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[dict] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "request_id": getattr(request.state, "request_id", ""),
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type="application/problem+json", headers=headers)


_HTTP_CODES = {
    401: "AUTH_TOKEN_EXPIRED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "NOT_FOUND",
    413: "FILE_TOO_LARGE",
    429: "RATE_LIMITED",
}


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app(request: Request, exc: AppError) -> JSONResponse:
        return problem(request, exc.status, exc.code, exc.title, exc.detail, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errs = [
            {"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return problem(request, 422, "VALIDATION_FAILED", "参数校验失败", errors=errs)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "INTERNAL_ERROR")
        return problem(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", path=request.url.path)  # No private exception/response text.
        return problem(request, 500, "INTERNAL_ERROR", "服务内部错误")


RATE_RESPONSES = {
    429: {
        "description": "RATE_LIMITED: configurable Redis sliding-window limit exceeded",
        "headers": {"Retry-After": {"schema": {"type": "integer", "minimum": 1}, "description": "Seconds"}},
        "content": {
            "application/problem+json": {
                "schema": {
                    "type": "object",
                    "required": ["type", "title", "status", "code", "request_id"],
                    "properties": {
                        "status": {"type": "integer", "const": 429},
                        "code": {"type": "string", "const": "RATE_LIMITED"},
                        "type": {"type": "string"},
                        "title": {"type": "string"},
                        "request_id": {"type": "string"},
                    },
                }
            }
        },
    },
    503: {
        "description": "RATE_LIMIT_UNAVAILABLE (fail closed), or MODEL_UNAVAILABLE on LLM paths",
        "content": {"application/problem+json": {"schema": {"type": "object"}}},
    },
}


VALIDATION_RESPONSE = {
    "description": "VALIDATION_FAILED: RFC 9457 problem+json",
    "content": {
        "application/problem+json": {
            "schema": {
                "type": "object",
                "required": ["type", "title", "status", "code", "request_id"],
                "properties": {
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"type": "integer"},
                    "code": {"type": "string"},
                    "request_id": {"type": "string"},
                    "errors": {"type": "array", "items": {"type": "object"}},
                },
            }
        }
    },
}
