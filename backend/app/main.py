from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core import rate_limit
from .core.config import settings
from .core.database import connect_db, close_db
from .routers import auth, catalog, customers, documents, signing, uploads, installations, inventory, users
from .models.customer import field_label


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(title="Solar Docs API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    """
    CSRF guard. The auth cookie is SameSite=None (kept so login also works
    when the API is reached on its own domain rather than through the frontend's
    /api proxy), so a browser attaches it even to requests started by some
    other website. CORS stops that site from *reading* responses, but "simple"
    requests (form/multipart POSTs, bodiless POSTs like generate / send-link)
    are still *executed*. Browsers always send an Origin header on cross-site
    writes, so refuse any write whose Origin isn't one of ours. Requests with no
    Origin (curl, server-to-server) can't carry a victim's cookie and pass.
    """
    origin = request.headers.get("origin")
    if request.method in _UNSAFE_METHODS and origin and origin not in settings.allowed_origins:
        return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
    return await call_next(request)

# Plain-language wording for the common validation failures.
_VALIDATION_WORDING = {
    "int_parsing": "must be a whole number",
    "int_from_float": "must be a whole number",
    "int_type": "must be a whole number",
    "float_parsing": "must be a number",
    "float_type": "must be a number",
    "greater_than_equal": "can't be negative",
    "greater_than": "must be more than 0",
    "less_than_equal": "is too large",
    "date_parsing": "must be a valid date",
    "date_from_datetime_parsing": "must be a valid date",
    "date_type": "must be a valid date",
    "value_error": None,  # use the validator's own message
}


@app.exception_handler(RequestValidationError)
async def readable_validation_error(request: Request, exc: RequestValidationError):
    """Turn Pydantic's error list into one sentence the UI can show as-is,
    e.g. "Phone must be a 10-digit mobile number; System Cost must be a whole number"."""
    parts = []
    for err in exc.errors():
        field = next((str(p) for p in reversed(err.get("loc", ())) if isinstance(p, str) and p.isupper()), None)
        if field is None:
            field = next((str(p) for p in reversed(err.get("loc", ())) if isinstance(p, str) and p != "body"), "Input")
        wording = _VALIDATION_WORDING.get(err.get("type"), err.get("msg"))
        if err.get("type") == "string_too_short":
            wording = f"must be at least {err.get('ctx', {}).get('min_length', 1)} characters"
        elif err.get("type") == "string_too_long":
            wording = f"must be at most {err.get('ctx', {}).get('max_length')} characters"
        if wording is None:
            wording = str(err.get("msg", "")).removeprefix("Value error, ")
            if wording.startswith("value is not a valid email address"):
                wording = "is not a valid email address"
        parts.append(f"{field_label(field) if field.isupper() else field.replace('_', ' ').capitalize()} {wording}")
    return JSONResponse(status_code=422, content={"detail": "; ".join(dict.fromkeys(parts)) or "Invalid input"})


@app.exception_handler(StarletteHTTPException)
async def log_auth_rejections(request: Request, exc: StarletteHTTPException):
    """
    Uvicorn's access log shows only "400 Bad Request". For sign-in / sign-up /
    account requests also log WHY (the same sentence the user sees), so a
    report like "I never got the code" can be traced from the server logs.
    The messages never contain passwords or codes.
    """
    path = request.url.path
    # /auth/me answers 401 on every page load while signed out: not worth logging.
    if path.startswith("/api/auth/") and 400 <= exc.status_code < 500 and path != "/api/auth/me":
        # ip / xff show which X-Forwarded-For entry is the real visitor, to
        # check TRUSTED_PROXY_HOPS is right behind the frontend's /api rewrite.
        xff = request.headers.get("x-forwarded-for", "")
        print(
            f"auth {request.method} {path} -> {exc.status_code}: {exc.detail} "
            f"(ip={rate_limit.client_ip(request)} xff={xff})"
        )
    return await http_exception_handler(request, exc)


app.include_router(auth.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(signing.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(installations.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(users.router, prefix="/api")


@app.get("/api/health")
@app.get("/health")  # the path Render's health check calls
async def health():
    return {"status": "ok"}
