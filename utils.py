# utils.py
import logging, time, os

def setup_logging(level="INFO"):
    logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                        level=getattr(logging, level.upper(), logging.INFO))

def now_ts():
    return int(time.time())
