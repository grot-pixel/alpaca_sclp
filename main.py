import alpaca_trade_api as tradeapi
import pandas as pd
import pandas_ta as ta
import json
import os
import math
import sys
from datetime import datetime
import pytz

# --- LOAD CONFIGURATION ---
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("CRITICAL ERROR: config.json not found. Exiting.")
    sys.exit(1)

# Extract config variables
SYMBOLS = config['SYMBOLS']
TARGET_GAIN = config['RISK_MANAGEMENT']['TARGET_GAIN_PCT']
STOP_LOSS = config['RISK_MANAGEMENT']['STOP_LOSS_PCT']
MAX_POSITIONS = config['RISK_MANAGEMENT']['MAX_CONCURRENT_POSITIONS']
USD_PER_TRADE = config['RISK_MANAGEMENT']['USD_PER_TRADE']
TIMEFRAME = config['SYSTEM']['TIMEFRAME']

# --- API CONNECTION ---
# Checks if running in Paper or Live mode based on Key format
BASE_URL = 'https://paper-api.alpaca.markets' if 'paper' in os.getenv('APCA_API_KEY_ID', '').lower() else 'https://api.alpaca.markets'

api = tradeapi.REST(
    os.getenv('APCA_API_KEY_ID'),
    os.getenv('APCA_API_SECRET_KEY'),
    base_url=BASE_URL,
    api_version='v2'
)

def get_data(symbol):
    """Fetch recent market data for analysis."""
    try:
        # Fetching 100 bars to ensure indicators have warmup data
        bars = api.get_bars(symbol, TIMEFRAME, limit=100, adjustment='raw').df
        if bars.empty: return None
        return bars
    except Exception as e:
        print(f"[{symbol}] Data fetch failed: {e}")
        return None

def analyze_market(df):
    """
    Aggressive Technical Analysis
    Returns: 'BUY', 'SELL', or None
    """
    # Calculate RSI
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # Calculate Bollinger Bands
    bb = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bb], axis=1)
    
    # Define columns dynamically from pandas_ta output
    # Usually: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
    lower_band = df[f'BBL_20_2.0']
    upper_band = df[f'BBU_20_2.0']

    current = df.iloc[-1]
    
    # STRATEGY 1: Oversold Reversal (Sniper Entry)
    # Price is below lower band AND RSI is crushed (<30)
    if current['close'] < current[lower_band.name] and current['RSI'] < config['SYSTEM']['RSI_OVERSOLD']:
        return 'BUY'

    # STRATEGY 2: Momentum Surge (Trend Following)
    # Price broke upper band AND RSI indicates strength but not total exhaustion
    if current['close'] > current[upper_band.name] and \
       config['SYSTEM']['RSI_MOMENTUM_MIN'] < current['RSI'] < config['SYSTEM']['RSI_MOMENTUM_MAX']:
        return 'BUY'

    return None

def execute_bracket_order(symbol, price):
    """Submits a smart OTOCO (One-Triggers-One-Cancels-Other) order."""
    
    # 1. Check liquidity/buying power
    account = api.get_account()
    buying_power = float(account.regt_buying_power)
    
    if buying_power < USD_PER_TRADE:
        print(f"SKIPPING {symbol}: Insufficient buying power (${buying_power}).")
        return

    # 2. Calculate Share Count
    qty = math.floor(USD_PER_TRADE / price)
    if qty < 1:
        print(f"SKIPPING {symbol}: Price too high for trade size.")
        return

    # 3. Calculate Exits
    take_profit = round(price * (1 + TARGET_GAIN), 2)
    stop_loss = round(price * (1 - STOP_LOSS), 2)

    print(f" >> EXECUTING BUY: {symbol} x {qty} @ ${price}")
    print(f"    TARGET: ${take_profit} (+0.5%) | STOP: ${stop_loss} (-1.5%)")

    try:
        api.submit_order(
            symbol=symbol,
            qty=qty,
            side='buy',
            type='market',
            time_in_force='day',
            order_class='bracket',
            take_profit={'limit_price': take_profit},
            stop_loss={'stop_price': stop_loss}
        )
        print(f"    SUCCESS: Bracket order placed for {symbol}.")
    except Exception as e:
        print(f"    FAILED: {e}")

def run_trading_cycle():
    print(f"--- SCAN STARTED: {datetime.now(pytz.utc)} ---")
    
    # Check Market Status
    clock = api.get_clock()
    if not clock.is_open:
        print("Market Closed. Scanning anyway for testing/extended hours logic (if enabled).")

    # Check Active Positions
    positions = api.list_positions()
    current_symbols = [p.symbol for p in positions]
    print(f"Current Positions: {len(current_symbols)}/{MAX_POSITIONS} {current_symbols}")

    if len(current_symbols) >= MAX_POSITIONS:
        print("Max positions reached. No new trades this cycle.")
        return

    # Scan Watchlist
    for symbol in SYMBOLS:
        if symbol in current_symbols:
            continue
            
        df = get_data(symbol)
        if df is None: continue
        
        signal = analyze_market(df)
        current_price = df.iloc[-1]['close']
        
        if signal == 'BUY':
            print(f"SIGNAL DETECTED for {symbol}: {signal}")
            execute_bracket_order(symbol, current_price)
            
            # Stop scanning if we hit max positions mid-loop
            if len(api.list_positions()) >= MAX_POSITIONS:
                break
        else:
            # Concise log for no-signal
            pass 

    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run_trading_cycle()
