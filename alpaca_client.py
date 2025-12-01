# alpaca_client.py
"""
Alpaca client wrapper.
- Uses APCA_API_KEY_1 / APCA_API_SECRET_1 (GitHub Secrets) or falls back to legacy env names.
- Defaults to PAPER mode unless MODE env or config.json requests otherwise.
- Does NOT pass unsupported 'base_url' kwarg to TradingClient.
- Includes retry wrapper for orders.
"""
import os
import json
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

logger = logging.getLogger(__name__)

# credentials (prefer GitHub Secrets-style names)
API_KEY = os.environ.get("APCA_API_KEY_1") or os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
API_SECRET = os.environ.get("APCA_API_SECRET_1") or os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
API_BASE_CANDIDATE = os.environ.get("APCA_BASE_URL_1") or os.environ.get("ALPACA_API_BASE") or os.environ.get("APCA_API_BASE_URL")
# MODE env override (PAPER or LIVE). If not set, fall back to config.json
ENV_MODE = os.environ.get("MODE", None)

# Attempt to load config.json's MODE safely (but do not require config file)
CONFIG_PATH = os.path.join(os.getcwd(), "config.json")
_config_mode = None
try:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
            _config_mode = cfg.get("MODE", None)
except Exception as e:
    logger.warning("Could not load config.json to determine MODE: %s", e)

# Decide whether to use paper True/False
# Priority: ENV_MODE -> config.json MODE -> guess from APCA_BASE_URL_1 (paper in url) -> default PAPER
def _is_paper_mode():
    if ENV_MODE:
        return str(ENV_MODE).strip().upper() == "PAPER"
    if _config_mode:
        return str(_config_mode).strip().upper() == "PAPER"
    if API_BASE_CANDIDATE and "paper" in API_BASE_CANDIDATE.lower():
        return True
    return True  # default to PAPER for safety

PAPER_MODE = _is_paper_mode()

if not API_KEY or not API_SECRET:
    logger.warning(
        "Alpaca API key/secret not set. Provide APCA_API_KEY_1 & APCA_API_SECRET_1 (GitHub Secrets) or ALPACA_API_KEY_ID & ALPACA_API_SECRET_KEY locally."
    )

trading_client = None
historical_data_client = None

try:
    # TradingClient signature does not accept base_url; use paper flag.
    trading_client = TradingClient(API_KEY, API_SECRET, paper=PAPER_MODE)
    historical_data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
    logger.info("Initialized Alpaca clients (paper=%s)", PAPER_MODE)
except TypeError as e:
    # Defensive fallback if TradingClient signature differs; re-raise after logging
    logger.exception("TradingClient initialization TypeError: %s", e)
    raise
except Exception as e:
    logger.exception("Failed to initialize Alpaca clients: %s", e)
    trading_client = None
    historical_data_client = None

# Retry wrapper for transient network errors and rate-limits
@retry(wait=wait_exponential(multiplier=0.5, min=1, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(Exception))
def submit_order_safe(func, *args, **kwargs):
    return func(*args, **kwargs)

def get_account():
    if trading_client is None:
        raise RuntimeError("Trading client not initialized.")
    return trading_client.get_account()

def list_positions():
    if trading_client is None:
        return []
    try:
        return trading_client.get_all_positions()
    except Exception as e:
        logger.exception("Error listing positions: %s", e)
        return []

def get_latest_quote(symbol: str):
    if historical_data_client is None:
        logger.debug("Historical data client not initialized.")
        return None
    try:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        return historical_data_client.get_stock_latest_quote(req)
    except Exception as e:
        logger.exception("Error getting latest quote for %s: %s", symbol, e)
        return None

def place_limit_order(symbol, qty, side, limit_price, time_in_force="day", order_class=None, take_profit=None, stop_loss=None, client_order_id=None):
    """
    Creates a Limit (or bracket) order using alpaca-py TradingClient. Uses retry wrapper.
    """
    if trading_client is None:
        raise RuntimeError("Trading client not initialized.")
    from alpaca.trading.requests import LimitOrderRequest, OrderSide, TimeInForce
    side_obj = OrderSide.SELL if side.lower() == "sell" else OrderSide.BUY
    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side_obj,
        time_in_force=TimeInForce.DAY,
        limit_price=str(limit_price)
    )

    if order_class == "bracket" and (take_profit is not None or stop_loss is not None):
        # attach bracket objects
        req.order_class = "bracket"
        from alpaca.trading.requests import TakeProfit, StopLoss
        if take_profit is not None:
            req.take_profit = TakeProfit(limit_price=str(take_profit))
        if stop_loss is not None:
            req.stop_loss = StopLoss(stop_price=str(stop_loss))

    return submit_order_safe(trading_client.submit_order, order_data=req, client_order_id=client_order_id)

def cancel_order(order_id):
    if trading_client is None:
        return
    try:
        trading_client.cancel_order(order_id)
    except Exception as e:
        logger.exception("Cancel order error: %s", e)

def get_order(order_id):
    if trading_client is None:
        return None
    try:
        return trading_client.get_order_by_id(order_id)
    except Exception as e:
        logger.exception("Get order error: %s", e)
        return None
