# alpaca_client.py — FINAL FIXED VERSION FOR ALPACA-PY 0.43.2

import os
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

logger = logging.getLogger(__name__)

# Prefer GitHub Secrets if present
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

MODE = os.environ.get("BOT_MODE", "PAPER").upper()

# True = paper endpoint, False = live endpoint
USE_PAPER = MODE != "LIVE"

logger.info(f"Initializing TradingClient – PAPER={USE_PAPER}")

try:
    trading_client = TradingClient(
        API_KEY,
        API_SECRET,
        paper=USE_PAPER
    )
except Exception as e:
    logger.error(f"Failed to initialize TradingClient: {e}")
    raise

# Historical data client
historical_data_client = StockHistoricalDataClient(API_KEY, API_SECRET)


# ----------- RETRY DECORATOR (Network, 429 API Rate Limits) -----------

@retry(
    wait=wait_exponential(multiplier=0.5, min=1, max=8),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type(Exception),
)
def submit_order_safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.exception(f"Order submission error: {e}")
        raise


# ----------- API WRAPPERS -----------

def get_account():
    try:
        return trading_client.get_account()
    except Exception as e:
        logger.error(f"Error fetching account: {e}")
        return None


def list_positions():
    try:
        return trading_client.get_all_positions()
    except Exception as e:
        logger.error(f"Error loading positions: {e}")
        return []


def get_latest_quote(symbol: str):
    try:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        return historical_data_client.get_stock_latest_quote(req)
    except Exception as e:
        logger.error(f"Quote fetch failed for {symbol}: {e}")
        return None


def place_limit_order(symbol, qty, side, limit_price):
    from alpaca.trading.requests import LimitOrderRequest, OrderSide, TimeInForce

    side_obj = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

    order = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side_obj,
        limit_price=str(limit_price),
        time_in_force=TimeInForce.DAY
    )

    return submit_order_safe(trading_client.submit_order, order_data=order)


def cancel_order(order_id):
    try:
        trading_client.cancel_order_by_id(order_id)
    except Exception as e:
        logger.error(f"Cancel order failed: {e}")


def get_order(order_id):
    try:
        return trading_client.get_order_by_id(order_id)
    except Exception as e:
        logger.error(f"Get order failed: {e}")
        return None
