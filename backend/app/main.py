from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from .core.config import settings
from .core.database import connect_db, close_db
from .routers import auth, customers, documents, signing, uploads, installations, inventory, users


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
    CSRF guard. The auth cookie is SameSite=None (frontend and API live on
    different sites), so a browser attaches it even to requests started by some
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

app.include_router(auth.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(signing.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(installations.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(users.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
