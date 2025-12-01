# risk_manager.py
import json
import logging
from alpaca_client import list_positions, get_account

logger = logging.getLogger(__name__)
CONFIG_PATH = "config.json"

def _load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.exception("config.json is not valid JSON: %s", e)
        raise
    except FileNotFoundError:
        logger.exception("config.json not found at %s", CONFIG_PATH)
        raise
    except Exception as e:
        logger.exception("Unexpected error loading config.json: %s", e)
        raise

def can_enter_position(symbol, config=None):
    if config is None:
        config = _load_config()

    try:
        positions = list_positions()
    except Exception as e:
        logger.warning("Could not list positions (assuming zero): %s", e)
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

    # Basic daily-loss/account checks could go here. For now, allow entry.
    return True

def get_position_size_usd(symbol, config=None):
    if config is None:
        config = _load_config()
    return config.get("MAX_POSITION_SIZE_USD", 2000)
