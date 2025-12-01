# strategy.py
import logging
from alpaca_client import get_latest_quote
from order_manager import submit_scalp_order
from risk_manager import can_enter_position, get_position_size_usd
from decimal import Decimal

logger = logging.getLogger(__name__)

def compute_signal(symbol):
    """
    Lightweight micro-scalp signal based on last trade vs bid/ask skew.
    Returns: (signal_str or None, confidence 0..1)
    """
    quote = get_latest_quote(symbol)
    if not quote:
        return None, 0.0

    last = None
    if hasattr(quote, 'last') and quote.last and getattr(quote.last, 'price', None) is not None:
        last = quote.last.price

    ask = getattr(quote, 'ask_price', None) or last
    bid = getattr(quote, 'bid_price', None) or last

    if last is None or ask is None or bid is None:
        return None, 0.0

    try:
        last_d = Decimal(str(last))
        ask_d = Decimal(str(ask))
        bid_d = Decimal(str(bid))
        spread = (ask_d - bid_d) if (ask_d - bid_d) > 0 else Decimal("1e-9")
        rel = float((last_d - bid_d) / spread)
    except Exception:
        return None, 0.0

    confidence = max(0.0, min(1.0, abs(rel - 0.5) * 2.0))
    if rel > 0.6:
        return "buy", confidence
    if rel < 0.4:
        return "sell", confidence
    return None, 0.0

def execute_scan(symbols, config, account):
    results = []
    for sym in symbols:
        try:
            sig, conf = compute_signal(sym)
            if not sig:
                continue

            if not can_enter_position(sym, config):
                logger.debug("Risk manager blocked entry for %s", sym)
                continue

            size_usd = get_position_size_usd(sym, config)
            quote = get_latest_quote(sym)
            if not quote:
                logger.debug("No quote for %s", sym)
                continue

            price = None
            if hasattr(quote, 'last') and quote.last and getattr(quote.last, 'price', None) is not None:
                price = quote.last.price
            else:
                price = getattr(quote, 'ask_price', None) or getattr(quote, 'bid_price', None)

            if not price or price <= 0:
                logger.debug("Invalid price for %s, skipping", sym)
                continue

            qty = max(1, int(size_usd / price))
            target_pct = config.get("TRADE_TARGET_PER_TRADE", 0.005)
            slippage = config.get("SLIPPAGE_PCT", 0.002)
            limit_offset = config.get("LIMIT_OFFSET_TICKS", 0.01)
            side = "buy" if sig == "buy" else "sell"

            order = submit_scalp_order(sym, qty, side, target_pct, slippage, bracket=True, limit_offset_ticks=limit_offset)
            results.append({"symbol": sym, "signal": sig, "confidence": conf, "qty": qty, "order": str(order)})
        except Exception as e:
            logger.exception("Error scanning %s: %s", sym, e)
    return results
