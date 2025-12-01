# alpaca_client.py (FIXED FOR alpaca-py 0.43.2)
import os
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

logger = logging.getLogger(__name__)

# ENV VARS (GitHub Secrets preferred)
API_KEY = (
    os.environ.get("APCA_API_KEY_1")
    or os.environ.get("ALPACA_API_KEY_ID")
    or os.environ.get("ALPACA_API_KEY")
)
API_SECRET = (
    os.environ.get("APCA_API_SECRET_1")
    or os.environ.get("ALPACA_API_SECRET_KEY")
    or os.environ.get("ALPACA_API_SECRET")
)
API_BASE = (
    os.environ.get("APCA_BASE_URL_1")
    or os.environ.get("ALPACA_API_BASE")
)

if not API_KEY or not API_SECRET:
    logger.error("Missing Alpaca API keys. Did you set GitHub secrets?")
    raise SystemExit(1)

# -----------------------------
#   Determine live vs paper
# -----------------------------
use_paper = True

if API_BASE:
    if "paper" in API_BASE:
        use_paper = True
    else:
        use_paper = False

trading_client = TradingClient(
    API_KEY,
    API_SECRET,
    paper=use_paper
)

historical_data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# Safe retry wrapper
@retry(
    wait=wait_exponential(multiplier=0.5, min=1, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(Exception)
)
def submit_order_safe(order_fn, *args, **kwargs):
    try:
        return order_fn(*args, **kwargs)
    except Exception as e:
        logger.exception("Order submission failed: %s", e)
        raise

def get_account():
    return trading_client.get_account()

def list_positions():
    try:
        return trading_client.get_all_positions()
    except Exception as e:
        logger.exception(e)
        return []

def get_latest_quote(symbol: str):
    try:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        return historical_data_client.get_stock_latest_quote(req)
    except Exception as e:
        logger.exception("Failed getting quote for %s: %s", symbol, e)
        return None

def place_limit_order(symbol, qty, side, limit_price, **kwargs):
    from alpaca.trading.requests import LimitOrderRequest, OrderSide, TimeInForce

    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL if side.lower() == "sell" else OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        limit_price=str(limit_price)
    )

    return submit_order_safe(trading_client.submit_order, order_data=req)

def cancel_order(order_id):
    try:
        trading_client.cancel_order(order_id)
    except Exception as e:
        logger.exception(e)

def get_order(order_id):
    try:
        return trading_client.get_order_by_id(order_id)
    except Exception as e:
        logger.exception(e)
        return None
