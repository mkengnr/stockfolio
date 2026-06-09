from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Reject cross-site mutations from browsers (CSRF defense in depth).

    Cookie auth relies on SameSite=Lax; this adds an explicit server-side
    check. Requests without Origin and Referer (CLI clients, tests) are
    allowed — browsers always attach Origin to cross-site mutations.
    """

    def __init__(self, app, allowed_origins: list[str]):
        super().__init__(app)
        self.allowed_origins = {origin.rstrip("/") for origin in allowed_origins}

    async def dispatch(self, request: Request, call_next):
        if request.method in MUTATING_METHODS and not self._is_trusted(request):
            return JSONResponse(
                status_code=403,
                content={"detail": "Origin not allowed"},
            )
        return await call_next(request)

    def _is_trusted(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if origin is not None:
            return origin.rstrip("/") in self.allowed_origins
        referer = request.headers.get("referer")
        if referer is not None:
            parts = urlsplit(referer)
            return f"{parts.scheme}://{parts.netloc}" in self.allowed_origins
        return True
