# risk_manager.py
import json, logging
from alpaca_client import list_positions, get_account

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.json"

def _load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def can_enter_position(symbol, config=None):
    """
    Basic gating:
    - Respect MAX_SIMULTANEOUS_POSITIONS
    - Don't open another position in same symbol
    - Optional: evaluate account equity vs MAX_DAILY_LOSS_USD (placeholder)
    """
    if config is None:
        config = _load_config()

    try:
        positions = list_positions()
    except Exception:
        positions = []

    if len(positions) >= config.get("MAX_SIMULTANEOUS_POSITIONS", 6):
        logger.debug("Max simultaneous positions reached: %d >= %d", len(positions), config.get("MAX_SIMULTANEOUS_POSITIONS", 6))
        return False

    for p in positions:
        try:
            if getattr(p, "symbol", None) == symbol:
                logger.debug("Existing position detected in %s, skipping.", symbol)
                return False
        except Exception:
            continue

    # check for daily loss / account equity in a simple way; advanced monitoring should be added
    try:
        account = get_account()
        # account.equity may be available; skip heavy checks here if not
        # placeholder for advanced rules
    except Exception:
        pass

    return True

def get_position_size_usd(symbol, config=None):
    if config is None:
        config = _load_config()
    return config.get("MAX_POSITION_SIZE_USD", 2000)
