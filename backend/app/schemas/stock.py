from pydantic import BaseModel

from app.models.holding import Currency, Market


class StockSearchOut(BaseModel):
    ticker: str
    name: str
    market: Market
    currency: Currency

    model_config = {"from_attributes": True}
