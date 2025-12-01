# bot.py
import argparse
import logging
import time
from utils import setup_logging
from alpaca_client import get_account
from strategy import execute_scan
from risk_manager import _load_config

setup_logging("INFO")
logger = logging.getLogger("bot")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one scan and exit (useful for GitHub Action invocation).")
    args = parser.parse_args()

    try:
        config = _load_config()
    except Exception as e:
        logger.exception("Could not load config.json; exiting. Fix config.json syntax then retry. Error: %s", e)
        return

    symbols = config.get("SYMBOLS", [])
    interval = config.get("SCAN_INTERVAL_SECONDS", 300)
    logger.info("Starting bot in %s mode. Scanning %d symbols every %s seconds", config.get("MODE", "PAPER"), len(symbols), interval)

    if args.once:
        try:
            acc = None
            try:
                acc = get_account()
            except Exception as e:
                logger.debug("Failed to fetch account; continuing with scan. Error: %s", e)
            res = execute_scan(symbols, config, acc)
            logger.info("One-shot scan results: %s", res)
            return
        except Exception as e:
            logger.exception("One-shot execution failed: %s", e)
            return

    # Long-running loop (for local runs)
    while True:
        try:
            acc = None
            try:
                acc = get_account()
            except Exception:
                logger.debug("Account fetch failed; proceeding with scan.")
            execute_scan(symbols, config, acc)
        except Exception as e:
            logger.exception("Main loop error: %s", e)
        time.sleep(interval)

if __name__ == "__main__":
    main()
