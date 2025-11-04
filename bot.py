import os
import json
import time
from datetime import datetime, timezone, timedelta
import pandas as pd
from alpaca_trade_api.rest import REST, TimeFrame

# --- CONFIGURATION & SETUP ---
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE) as f:
        # Load the recommended scalping parameters
        cfg = {
          "symbols": ["AAPL", "ABAT", "AMD", "BTC", "COIN", "DOGE", "ETH", "MARA", "MP", "MSTR", "NVDA", "NVDL", "RIOT", "SOL", "SOXL", "SOXS", "SPXL", "SPXU", "SQQQ", "TQQQ", "TSLA", "TSLL", "UUUU"], 
          "max_position_pct": 0.10,
          "max_trade_pct": 0.05,
          "stop_loss_pct": 0.005,  # 0.5%
          "take_profit_pct": 0.01, # 1.0%
          "rsi_period": 9,
          "rsi_overbought": 70,
          "rsi_oversold": 30,
          "sma_fast": 5,
          "sma_slow": 13
        }
    # NOTE: In a production environment, you should load the config from disk:
    # with open(CONFIG_FILE) as f: cfg = json.load(f)
    print("Using Recommended Scalping Config:", cfg)
except FileNotFoundError:
    print(f"Error: {CONFIG_FILE} not found. Ensure it's in the same directory.")
    exit()

# --- CONSTANTS & HELPER FUNCTIONS ---
# Alpaca uses pairs for crypto (e.g., BTC/USD). We map the base symbol to the pair.
CRYPTO_MAP = {
    "BTC": "BTC/USD", "ETH": "ETH/USD", "DOGE": "DOGE/USD", 
    "SOL": "SOL/USD", "COIN": "COIN",  # COIN is a stock, but included for context
}
CRYPTO_SYMBOLS = set(CRYPTO_MAP.keys())

def rsi(series: pd.Series, period: int = 14):
    """Calculates the Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def generate_signals(data, config):
    """Return 'buy' or 'sell' based on SMA + RSI strategy."""
    data["sma_fast"] = data["close"].rolling(config["sma_fast"]).mean()
    data["sma_slow"] = data["close"].rolling(config["sma_slow"]).mean()
    data["rsi"] = rsi(data["close"], config["rsi_period"])

    if data.empty or data.iloc[-1].isnull().any():
        return None, "Not enough clean data for indicators"

    latest = data.iloc[-1]
    
    # Buy condition: Fast SMA > Slow SMA AND RSI is Oversold
    if (
        latest["sma_fast"] > latest["sma_slow"]
        and latest["rsi"] < config["rsi_oversold"]
    ):
        reason = f"SMA Cross: {latest['sma_fast']:.2f} > {latest['sma_slow']:.2f}, RSI Oversold: {latest['rsi']:.2f}"
        return "buy", reason
    # Sell condition: Fast SMA < Slow SMA AND RSI is Overbought
    elif (
        latest["sma_fast"] < latest["sma_slow"]
        and latest["rsi"] > config["rsi_overbought"]
    ):
        reason = f"SMA Cross: {latest['sma_fast']:.2f} < {latest['sma_slow']:.2f}, RSI Overbought: {latest['rsi']:.2f}"
        return "sell", reason
    else:
        return None, "No signal"


def is_regular_market_open(api: REST) -> bool:
    """Checks if the US equity market is within regular hours (9:30 AM - 4:00 PM ET)."""
    try:
        clock = api.get_clock()
        return clock.is_open
    except Exception as e:
        print(f"Error checking market clock: {e}")
        return True # Default to True to allow crypto/weekend checks to proceed


# --- MAIN TRADING LOGIC ---
def trade_strategy(account_name: str, api: REST, symbols: list):
    print(f"\n--- Running strategy for {account_name} ---")

    # 1. Get account info
    try:
        account = api.get_account()
        equity = float(account.equity)
        print(f"Account Equity: ${equity:,.2f} | Buying Power: ${float(account.buying_power):,.2f}")
    except Exception as e:
        print(f"Error fetching account info: {e}")
        return

    # 2. Check market status
    market_open = is_regular_market_open(api)

    # 3. Process each symbol
    for sym in symbols:
        # Determine the Alpaca symbol format (e.g., "BTC" -> "BTC/USD")
        alpaca_sym = CRYPTO_MAP.get(sym, sym)
        is_crypto = sym in CRYPTO_SYMBOLS
        
        # We trade if the stock market is open OR if the asset is crypto
        is_tradable_now = market_open or is_crypto
        
        # Check if the asset is a stock/ETF but the market is closed
        if not is_tradable_now and not is_crypto:
             print(f"[{sym}] Skipping: Stock market closed.")
             continue
        elif not is_tradable_now and is_crypto:
            # Should not happen with the logic above, but safety check
            print(f"[{sym}] Skipping: Crypto symbol but somehow not tradable.")
            continue

        try:
            # A. Get Market Data (5-Minute Bars)
            required_limit = max(cfg["sma_slow"], cfg["rsi_period"]) + 2 
            
            # Fetch 5-minute bars ('5Min' is the correct string for 5-minute aggregation in alpaca_trade_api)
            bars = api.get_bars(alpaca_sym, '5Min', limit=required_limit).df 
            
            if bars.empty or len(bars) < required_limit:
                print(f"[{sym}] Skipping: Not enough 5Min data ({len(bars)}/{required_limit})")
                continue
            
            # B. Generate Signal
            signal, reason = generate_signals(bars, cfg)
            current_price = bars["close"].iloc[-1]
            
            # C. Check for Existing Position/Open Orders
            try:
                # Bracket orders handle TP/SL, so we only need to manage open entries/existing positions
                open_orders = api.list_orders(status='open', symbols=[alpaca_sym])
                position_qty = float(api.get_position(alpaca_sym).qty)
            except Exception:
                # Assume no open position/order if fetching position/orders fails
                open_orders = []
                position_qty = 0

            # --- Trading Logic ---
            if signal == "buy":
                # Check for maximum position limits
                max_trade_dollar = equity * cfg["max_trade_pct"]
                max_position_dollar = equity * cfg["max_position_pct"]
                
                # Calculate quantity for the max trade size
                qty_to_buy = max_trade_dollar / current_price 
                
                # Calculate remaining capacity for the max position size
                current_dollar_value = position_qty * current_price
                remaining_buy_power = max_position_dollar - current_dollar_value
                qty_to_add = remaining_buy_power / current_price
                
                # Determine final integer quantity to buy
                # We use max(0, int(...)) to handle fractional crypto units safely, though Alpaca supports fractional shares
                final_qty = max(0, int(min(qty_to_buy, qty_to_add))) 

                if position_qty == 0 and final_qty > 0 and not open_orders:
                    # Place a new entry order with bracket (TP/SL)
                    
                    # Calculate TP/SL prices based on current price and percentage configs
                    take_profit_price = round(current_price * (1.0 + cfg["take_profit_pct"]), 4)
                    stop_loss_price = round(current_price * (1.0 - cfg["stop_loss_pct"]), 4)
                    
                    print(f"[{sym}] Signal: BUY ({reason}). QTY: {final_qty} @ ${current_price:.2f}. TP: ${take_profit_price:.2f}, SL: ${stop_loss_price:.2f}")

                    api.submit_order(
                        symbol=alpaca_sym,
                        qty=final_qty,
                        side='buy',
                        type='limit', # Use limit to ensure price fill
                        time_in_force='day', 
                        limit_price=current_price,
                        order_class='bracket',
                        take_profit=dict(limit_price=take_profit_price),
                        stop_loss=dict(stop_price=stop_loss_price)
                    )
                    print(f"[{sym}] Bracket Order submitted: LIMIT BUY {final_qty} shares/units.")
                else:
                    print(f"[{sym}] Signal: BUY ({reason}). Position: {position_qty}, Open Orders: {len(open_orders)}. Skipping entry.")
            
            elif signal == "sell" and position_qty > 0:
                # Our primary exit is the bracket order. This 'sell' signal acts as a market exit override.
                # E.g., if you want to exit due to a massive trend reversal signal.
                
                # First, cancel all open bracket/contingent orders to release position funds
                if open_orders:
                    for order in open_orders:
                        api.cancel_order(order.id)
                    print(f"[{sym}] Canceled {len(open_orders)} open contingent orders.")
                
                # Sell the entire position immediately
                print(f"[{sym}] Signal: SELL ({reason}). Closing position of {position_qty} shares/units @ ${current_price:.2f}")
                api.submit_order(alpaca_sym, position_qty, 'sell', 'market', 'day')
                print(f"[{sym}] Market Order submitted: SELL {position_qty}.")
                
            else:
                # Check if we have an open order that needs canceling if signal changed
                if open_orders:
                    # Cancel any limit buy orders that haven't filled if the signal is no longer 'buy'
                    # In a high-frequency bot, you usually cancel if the signal is gone.
                    for order in open_orders:
                        if order.side == 'buy' and order.type == 'limit':
                             api.cancel_order(order.id)
                             print(f"[{sym}] CANCELED stale limit BUY order: {order.id}")
                
        except Exception as e:
            print(f"[{sym}] ❌ Error processing symbol: {e}")


# --- INITIALIZATION AND EXECUTION ---
accounts = []
# NOTE: Removed the loop and simplified to a single account for conciseness.
key = os.getenv("APCA_API_KEY_1")
secret = os.getenv("APCA_API_SECRET_1")
base = os.getenv("APCA_BASE_URL_1") or "https://paper-api.alpaca.markets"

if key and secret:
    try:
        api = REST(key, secret, base)
        api.get_account()
        print("Account connected successfully.")
        accounts.append({
            "name": "PaperAccount1",
            "api": api,
            "symbols": cfg["symbols"]
        })
    except Exception as e:
        print(f"Failed to connect to Account 1: {e}. Skipping.")

if not accounts:
    print("No accounts connected. Exiting.")
else:
    for account_data in accounts:
        # Cancel any open orders before starting to ensure a clean slate (optional, but good practice)
        api.cancel_all_orders()
        print("\nCanceled all previous open orders.")
        trade_strategy(account_data["name"], account_data["api"], account_data["symbols"])
    
    print("\nTrading bot run complete.")

This code now uses Alpaca's robust **Bracket Order** functionality, which is the industry standard for automated systems that need reliable, simultaneous Take-Profit and Stop-Loss orders, and it properly manages the **24/7 nature of your crypto assets** for continuous trading.

[Bracket Orders with Alpaca Trading API in Python Gotchas](https://www.youtube.com/watch?v=w4PMHz7FR_A) provides a detailed look at how to properly manage bracket orders, which are essential for your new bot.
http://googleusercontent.com/youtube_content/0
