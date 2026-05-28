from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.holdings import router as holdings_router
from app.routers.tags import router as tags_router, share_router
from app.routers.admin import router as admin_router
from app.tasks.scheduler import start_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield


app = FastAPI(
    title="stockfolio",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(holdings_router)
app.include_router(tags_router)
app.include_router(share_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
