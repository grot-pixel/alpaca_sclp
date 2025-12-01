# bot.py
import argparse, json, logging, time
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

    config = _load_config()
    symbols = config.get("SYMBOLS", [])
    interval = config.get("SCAN_INTERVAL_SECONDS", 300)
    logger.info("Starting bot in %s mode. Scanning %d symbols every %s seconds",
                config.get("MODE", "PAPER"), len(symbols), interval)

    if args.once:
        try:
            acc = get_account()
        except Exception as e:
            logger.exception("Failed to fetch account: %s", e)
            acc = None
        res = execute_scan(symbols, config, acc)
        logger.info("One-shot scan results: %s", res)
        return

    # Long-running local loop
    while True:
        try:
            acc = None
            try:
                acc = get_account()
            except Exception:
                logger.debug("Account fetch failed; continuing with scan.")
            execute_scan(symbols, config, acc)
        except Exception as e:
            logger.exception("Main loop error: %s", e)
        time.sleep(interval)

if __name__ == "__main__":
    main()
