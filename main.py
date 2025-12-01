import alpaca_trade_api as tradeapi
import pandas as pd
import pandas_ta as ta
import os
import time
import math
from datetime import datetime, timedelta
import pytz

# --- CONFIGURATION ---
# Aggressive Tech & Crypto-related stocks for high volatility
SYMBOLS = ['NVDA', 'TSLA', 'AMD', 'COIN', 'MARA', 'PLTR', 'SOXL', 'TQQQ', 'MSTR']
TARGET_GAIN_PER_TRADE = 0.005  # 0.5%
STOP_LOSS_PCT = 0.015          # 1.5% (Wider stop to prevent shakeouts in volatile markets)
MAX_POSITIONS = 5              # Max concurrent trades to manage risk
USD_PER_TRADE = 2000           # Amount to bet per trade (Adjust based on your equity)
TIMEFRAME = '5Min'             # Fast timeframe

# --- API CONNECTION ---
api = tradeapi.REST(
    os.getenv('APCA_API_KEY_ID'),
    os.getenv('APCA_API_SECRET_KEY'),
    base_url='https://paper-api.alpaca.markets' if 'paper' in os.getenv('APCA_API_KEY_ID', '').lower() else 'https://api.alpaca.markets',
    api_version='v2'
)

def get_market_status():
    clock = api.get_clock()
    return clock.is_open

def get_data(symbol):
    try:
        # Get enough data for indicators
        bars = api.get_bars(symbol, TIMEFRAME, limit=100, adjustment='raw').df
        if bars.empty:
            return None
        return bars
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def analyze(df):
    # Aggressive Strategy: RSI + Bollinger Bands
    # We want to catch momentum or rapid reversals
    
    # Calculate Indicators
    df['RSI'] = ta.rsi(df['close'], length=14)
    bb = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bb], axis=1)
    
    # Rename BB columns for clarity
    df.rename(columns={
        'BBL_20_2.0': 'bb_lower',
        'BBM_20_2.0': 'bb_mid',
        'BBU_20_2.0': 'bb_upper'
    }, inplace=True)

    current = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None
    
    # LOGIC 1: Oversold Bounce (Aggressive Buy)
    # Price touched lower band and RSI is oversold (<30) turning up
    if current['close'] < current['bb_lower'] and current['RSI'] < 30:
        signal = 'BUY'
        print(f"Signal DETECTED: {signal} (Oversold Bounce)")

    # LOGIC 2: Momentum Breakout
    # Price broke upper band and RSI is strong but not exhausted (50 < RSI < 70)
    elif current['close'] > current['bb_upper'] and 50 < current['RSI'] < 75:
        signal = 'BUY'
        print(f"Signal DETECTED: {signal} (Momentum Breakout)")

    return signal, current['close']

def execute_trade(symbol, price):
    # Check buying power
    account = api.get_account()
    buying_power = float(account.regt_buying_power)
    
    if buying_power < USD_PER_TRADE:
        print(f"Insufficient funds for {symbol}. Skipping.")
        return

    # Calculate Quantity
    qty = math.floor(USD_PER_TRADE / price)
    if qty <= 0: return

    # Calculate Bracket Prices
    take_profit_price = round(price * (1 + TARGET_GAIN_PER_TRADE), 2)
    stop_loss_price = round(price * (1 - STOP_LOSS_PCT), 2)

    print(f"Executing BRACKET ORDER for {symbol} | Entry: {price} | TP: {take_profit_price} | SL: {stop_loss_price}")

    try:
        # Submit OTOCO (One-Triggers-One-Cancels-Other) Order
        # This is CRITICAL for GitHub Actions: The exit logic is stored on Alpaca, not your PC.
        api.submit_order(
            symbol=symbol,
            qty=qty,
            side='buy',
            type='market', # Aggressive entry
            time_in_force='gtc',
            order_class='bracket',
            take_profit={'limit_price': take_profit_price},
            stop_loss={'stop_price': stop_loss_price}
        )
        print(f"Trade submitted successfully for {symbol}")
    except Exception as e:
        print(f"Order failed for {symbol}: {e}")

def run_bot():
    print(f"--- Bot Starting: {datetime.now(pytz.utc)} ---")
    
    if not get_market_status():
        print("Market is closed. Checking for Extended Hours capability or exiting.")
        # Note: Regular Paper Trading often requires Market Hours. 
        # For Real money, you can enable extended_hours=True in submit_order.
        
    # Check current positions to manage risk
    positions = api.list_positions()
    current_holdings = [p.symbol for p in positions]
    
    if len(current_holdings) >= MAX_POSITIONS:
        print(f"Max positions reached ({len(current_holdings)}). Scanning for exits or waiting.")
        # Since we use bracket orders, exits are automatic. We just stop buying.
        return

    # Scan Assets
    for symbol in SYMBOLS:
        if symbol in current_holdings:
            print(f"Already holding {symbol}. Skipping.")
            continue
            
        print(f"Scanning {symbol}...")
        df = get_data(symbol)
        if df is None: continue
        
        signal, price = analyze(df)
        
        if signal == 'BUY':
            execute_trade(symbol, price)

    print("--- Scan Complete ---")

if __name__ == "__main__":
    run_bot()
