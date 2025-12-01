# Alpaca Micro-Scalp Trading Bot (PAPER-default)

**IMPORTANT: This repo is configured to default to PAPER mode.** That prevents accidental live trading.

## Setup
1. Add these GitHub Secrets to your repo:
   - `APCA_API_KEY_1`
   - `APCA_API_SECRET_1`
   - `APCA_BASE_URL_1` (optional; if you provide it and it contains "paper" we'll stay in paper; nonetheless default is PAPER)

2. Edit `config.json` if needed. Ensure it is valid JSON (no trailing commas).

3. Use the GitHub workflow (every 5 minutes) or run locally:
   ```bash
   export APCA_API_KEY_1="..."
   export APCA_API_SECRET_1="..."
   export APCA_BASE_URL_1="https://paper-api.alpaca.markets"
   pip install -r requirements.txt
   python bot.py --once
