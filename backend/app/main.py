from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings, validate_runtime_settings
from app.middleware import OriginValidationMiddleware
from app.routers.auth import router as auth_router
from app.routers.holdings import router as holdings_router
from app.routers.tags import router as tags_router, share_router
from app.routers.admin import router as admin_router
from app.routers.stocks import router as stocks_router
from app.routers.portfolio import router as portfolio_router
from app.routers.groups import router as groups_router
from app.routers.transactions import router as transactions_router
from app.tasks.scheduler import start_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_settings(settings)
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
app.add_middleware(OriginValidationMiddleware, allowed_origins=settings.allowed_origins)

app.include_router(auth_router)
app.include_router(holdings_router)
app.include_router(tags_router)
app.include_router(share_router)
app.include_router(admin_router)
app.include_router(stocks_router)
app.include_router(portfolio_router)
app.include_router(groups_router)
app.include_router(transactions_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
