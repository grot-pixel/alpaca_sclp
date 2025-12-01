# strategy.py
import logging
from alpaca_client import get_latest_quote
from order_manager import submit_scalp_order
from risk_manager import can_enter_position, get_position_size_usd
from decimal import Decimal

logger = logging.getLogger(__name__)

def compute_signal(symbol):
    """
    Lightweight micro-scalp signal:
    - Use latest quote and compare last trade position within bid/ask range.
    - If last price is near ask (aggressive buying), signal BUY.
    - If last price is near bid (aggressive selling), signal SELL.
    Returns (signal, confidence).
    """
    quote = get_latest_quote(symbol)
    if not quote:
        return None, 0.0

    last = None
    if hasattr(quote, 'last') and quote.last and getattr(quote.last, 'price', None):
        last = quote.last.price
    ask = getattr(quote, 'ask_price', None) or last
    bid = getattr(quote, 'bid_price', None) or last

    if last is None or ask is None or bid is None:
        return None, 0.0

    # normalize
    try:
        last_d = Decimal(str(last))
        ask_d = Decimal(str(ask))
        bid_d = Decimal(str(bid))
        spread = float(ask_d - bid_d) if (ask_d - bid_d) > 0 else 1e-9
        rel = float((last_d - bid_d) / spread)
    except Exception:
        return None, 0.0

    # map rel to confidence: 0.5 neutral -> 0, above more buy momentum, below more sell momentum
    confidence = max(0.0, min(1.0, abs(rel - 0.5) * 2.0))
    if rel > 0.6:
        return "buy", confidence
    if rel < 0.4:
        return "sell", confidence
    return None, 0.0

def execute_scan(symbols, config, account):
    """
    Scan a list of symbols, compute signals, risk-gate them, and submit orders.
    Returns a list of order result dicts.
    """
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
            from alpaca_client import get_latest_quote as _get_q
            quote = _get_q(sym)
            if not quote:
                logger.debug("No quote for %s at ordering time", sym)
                continue

            price = None
            if hasattr(quote, 'last') and quote.last and getattr(quote.last, 'price', None):
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
