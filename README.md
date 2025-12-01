# Alpaca Micro-Scalp Trading Bot

**WARNING: HIGH RISK** — This bot is an educational/scaffolding example. Always run in PAPER mode first.

## Quick start
1. Create a GitHub repo (public if you want free GitHub Actions minutes), add these files.
2. Put Alpaca API keys as GitHub Secrets:
   - `APCA_API_KEY_1`
   - `APCA_API_SECRET_1`
   - `APCA_BASE_URL_1` (optional; use Alpaca paper URL for paper trading)
3. Edit `config.json` for symbols, sizes, slippage, and risk limits.
4. Use the included GitHub Actions workflow to run a one-shot scan every 5 minutes (`.github/workflows/trigger.yml`).
   - Note: Frequent Actions runs consume CI minutes; public repos have free minutes for Actions.
5. Alternatively run locally:
   ```bash
   export APCA_API_KEY_1="..."
   export APCA_API_SECRET_1="..."
   export APCA_BASE_URL_1="https://paper-api.alpaca.markets"
   pip install -r requirements.txt
   python bot.py --once
