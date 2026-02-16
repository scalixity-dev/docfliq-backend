import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def error_envelope_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    try:
        return await call_next(request)
    except StarletteHTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.detail if isinstance(exc.detail, str) else "http_error",
                    "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                },
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    except Exception as exc:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {"code": "internal_error", "message": "An unexpected error occurred"},
                "request_id": getattr(request.state, "request_id", None),
            },
        )
