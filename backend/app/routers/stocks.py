from typing import Annotated
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.stock import StockSearchOut
from app.services.stock_fetcher import MAX_SEARCH_RESULTS, search_stocks

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search", response_model=list[StockSearchOut])
async def search(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    _current_user: User = Depends(get_current_user),
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_RESULTS)] = 10,
):
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=422,
            detail="Search query must not be blank",
        )
    return await asyncio.to_thread(search_stocks, query, limit)
