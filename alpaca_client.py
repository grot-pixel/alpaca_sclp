# alpaca_client.py (UPDATED to support APCA_API_* secrets)
import os, time, asyncio, logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

logger = logging.getLogger(__name__)

# Prefer GitHub Secrets-style names if present (user provided)
API_KEY = os.environ.get("APCA_API_KEY_1") or os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
API_SECRET = os.environ.get("APCA_API_SECRET_1") or os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
API_BASE = os.environ.get("APCA_BASE_URL_1") or os.environ.get("ALPACA_API_BASE") or os.environ.get("APCA_API_BASE_URL")

if not API_KEY or not API_SECRET:
    logger.warning("Alpaca API key/secret not set in env. Set APCA_API_KEY_1 & APCA_API_SECRET_1 (GitHub Secrets), or ALPACA_API_KEY_ID & ALPACA_API_SECRET_KEY locally.")

# alpaca-py TradingClient takes paper=True or base_url for endpoints. We'll default to paper mode unless APCA_BASE_URL_1 provided.
_trading_client_kwargs = {}
if API_BASE:
    # If user provided a custom base url (eg paper vs live), pass it explicitly
    trading_client = TradingClient(API_KEY, API_SECRET, paper=False, base_url=API_BASE)
else:
    # assume paper by default to be safe
    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)

historical_data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# Retry wrapper for transient network and 429s
@retry(wait=wait_exponential(multiplier=0.5, min=1, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type(Exception))
def submit_order_safe(order_request_fn, *args, **kwargs):
    """Call order_request_fn inside retry to handle transient 429s and network blips."""
    try:
        return order_request_fn(*args, **kwargs)
    except Exception as e:
        logger.exception("Order submission failed, will retry if transient: %s", e)
        raise

def get_account():
    return trading_client.get_account()

def list_positions():
    try:
        return trading_client.get_all_positions()
    except Exception as e:
        logger.exception("Error listing positions: %s", e)
        return []

def get_latest_quote(symbol: str):
    try:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        return historical_data_client.get_stock_latest_quote(req)
    except Exception as e:
        logger.exception("Error getting latest quote for %s: %s", symbol, e)
        return None

def place_limit_order(symbol, qty, side, limit_price, time_in_force="day", order_class=None, take_profit=None, stop_loss=None, client_order_id=None):
    from alpaca.trading.requests import LimitOrderRequest, OrderSide, TimeInForce
    side_obj = OrderSide.SELL if side.lower()=="sell" else OrderSide.BUY
    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side_obj,
        time_in_force=TimeInForce.DAY,
        limit_price=str(limit_price)
    )
    if order_class == "bracket" and (take_profit or stop_loss):
        req.order_class = "bracket"
        from alpaca.trading.requests import TakeProfit, StopLoss
        if take_profit:
            req.take_profit = TakeProfit(limit_price=str(take_profit))
        if stop_loss:
            req.stop_loss = StopLoss(stop_price=str(stop_loss))
    return submit_order_safe(trading_client.submit_order, order_data=req, client_order_id=client_order_id)

def cancel_order(order_id):
    try:
        trading_client.cancel_order(order_id)
    except Exception as e:
        logger.exception("Cancel order error: %s", e)

def get_order(order_id):
    try:
        return trading_client.get_order_by_id(order_id)
    except Exception as e:
        logger.exception("Get order error: %s", e)
        return None
