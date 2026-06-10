from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import settings
from .core.database import connect_db, close_db
from .routers import auth, customers, documents, signing, uploads


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

app.include_router(auth.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(signing.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
