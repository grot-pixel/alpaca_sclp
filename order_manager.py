# order_manager.py
import time, uuid, logging
from decimal import Decimal
from alpaca_client import place_limit_order, get_latest_quote
from utils import now_ts

logger = logging.getLogger(__name__)

def marketable_limit_price(side, last_trade_price, slippage_pct, limit_offset_ticks):
    """Compute a marketable limit price that attempts to get filled but protects from adverse slippage."""
    price = Decimal(str(last_trade_price))
    offset = Decimal(str(slippage_pct))
    tick = Decimal(str(limit_offset_ticks))
    if side.lower() == "buy":
        target = price * (1 + offset) + tick
    else:
        target = price * (1 - offset) - tick
    # round to 4 decimals to be safe for US equities
    return float(round(target, 4))

def submit_scalp_order(symbol, qty, side, target_pct, slippage_pct, bracket=True, limit_offset_ticks=0.0):
    """
    Submit a marketable limit order sized to qty, with bracket TP/SL if bracket=True.
    Returns the order object returned by Alpaca or None.
    """
    quote = get_latest_quote(symbol)
    if not quote:
        logger.warning("No quote available for %s", symbol)
        return None

    # try to get a usable last trade price; fall back to ask/bid if necessary
    last_price = None
    if hasattr(quote, 'last') and quote.last and getattr(quote.last, "price", None):
        last_price = quote.last.price
    else:
        last_price = getattr(quote, "ask_price", None) or getattr(quote, "bid_price", None)

    if not last_price:
        logger.warning("Quote has no usable price for %s", symbol)
        return None

    limit_price = marketable_limit_price(side, last_price, slippage_pct, limit_offset_ticks)
    client_order_id = f"scalp-{symbol}-{now_ts()}-{uuid.uuid4().hex[:6]}"

    # compute take profit and stop loss relative to limit price
    if side.lower() == "buy":
        take = limit_price * (1 + target_pct)
        stop = limit_price * (1 - (target_pct * 2))  # default wider stop
        try:
            order = place_limit_order(symbol, qty, "buy", limit_price, order_class="bracket",
                                      take_profit=take, stop_loss=stop, client_order_id=client_order_id)
            logger.info("Placed BUY bracket order %s qty=%s limit=%s TP=%s SL=%s", symbol, qty, limit_price, take, stop)
            return order
        except Exception as e:
            logger.exception("Failed to place buy order for %s: %s", symbol, e)
            return None
    else:
        take = limit_price * (1 - target_pct)
        stop = limit_price * (1 + (target_pct * 2))
        try:
            order = place_limit_order(symbol, qty, "sell", limit_price, order_class="bracket",
                                      take_profit=take, stop_loss=stop, client_order_id=client_order_id)
            logger.info("Placed SELL bracket order %s qty=%s limit=%s TP=%s SL=%s", symbol, qty, limit_price, take, stop)
            return order
        except Exception as e:
            logger.exception("Failed to place sell order for %s: %s", symbol, e)
            return None
