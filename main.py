from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
import pandas_ta as ta
import json
import os
import math
import sys
from datetime import datetime, timedelta
import pytz

# --- LOAD CONFIGURATION ---
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("CRITICAL ERROR: config.json not found. Exiting.")
    sys.exit(1)

SYMBOLS = config['SYMBOLS']
TARGET_GAIN = config['RISK_MANAGEMENT']['TARGET_GAIN_PCT']
STOP_LOSS = config['RISK_MANAGEMENT']['STOP_LOSS_PCT']
MAX_POSITIONS = config['RISK_MANAGEMENT']['MAX_CONCURRENT_POSITIONS']
USD_PER_TRADE = config['RISK_MANAGEMENT']['USD_PER_TRADE']

# --- API CLIENTS ---
api_key = os.getenv('APCA_API_KEY_ID')
api_secret = os.getenv('APCA_API_SECRET_KEY')
paper_mode = 'paper' in api_key.lower()

trade_client = TradingClient(api_key, api_secret, paper=paper_mode)
data_client = StockHistoricalDataClient(api_key, api_secret)

def get_data(symbol):
    """Fetch recent market data for analysis using StockHistoricalDataClient."""
    try:
        # Fetch last 100 bars (5-minute intervals)
        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute, # Using 5x 1min bars or 5min if available
            start=datetime.now(pytz.utc) - timedelta(hours=5),
            limit=100
        )
        bars = data_client.get_stock_bars(request_params)
        df = bars.df
        
        # Resample to 5Min if we get minute data, or ensure formatting
        if not df.empty:
            df = df.droplevel(0) # Remove symbol index if present
            # Basic cleanup
            df = df.resample('5min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
        return df
    except Exception as e:
        print(f"[{symbol}] Data fetch failed: {e}")
        return None

def analyze_market(df):
    """Aggressive Technical Analysis (RSI + Bollinger Bands)."""
    if len(df) < 20: return None # Not enough data

    # RSI
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # Bollinger Bands
    bb = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bb], axis=1)
    
    lower_band = df[f'BBL_20_2.0']
    upper_band = df[f'BBU_20_2.0']
    current = df.iloc[-1]
    
    # LOGIC 1: Oversold Bounce
    if current['close'] < current[lower_band.name] and current['RSI'] < config['SYSTEM']['RSI_OVERSOLD']:
        return 'BUY'

    # LOGIC 2: Momentum Breakout
    if current['close'] > current[upper_band.name] and \
       config['SYSTEM']['RSI_MOMENTUM_MIN'] < current['RSI'] < config['SYSTEM']['RSI_MOMENTUM_MAX']:
        return 'BUY'

    return None

def execute_bracket_order(symbol, price):
    """Submits a Bracket Order using the new Alpaca-py SDK."""
    
    # Check Buying Power
    account = trade_client.get_account()
    buying_power = float(account.regt_buying_power)
    
    if buying_power < USD_PER_TRADE:
        print(f"SKIPPING {symbol}: Insufficient BP (${buying_power}).")
        return

    qty = math.floor(USD_PER_TRADE / price)
    if qty < 1: return

    take_profit_price = round(price * (1 + TARGET_GAIN), 2)
    stop_loss_price = round(price * (1 - STOP_LOSS), 2)

    print(f" >> EXECUTING BUY: {symbol} x {qty} @ ${price}")
    
    # Order Request
    order_data = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class='bracket',
        take_profit=TakeProfitRequest(limit_price=take_profit_price),
        stop_loss=StopLossRequest(stop_price=stop_loss_price)
    )

    try:
        trade_client.submit_order(order_data)
        print(f"    SUCCESS: Bracket order placed for {symbol}.")
    except Exception as e:
        print(f"    FAILED: {e}")

def run_trading_cycle():
    print(f"--- SCAN STARTED: {datetime.now(pytz.utc)} ---")
    
    # Check Market Status
    clock = trade_client.get_clock()
    if not clock.is_open:
        print("Market Closed. (Note: Crypto trades 24/7 if enabled).")
        # For pure stock bots, you might return here. 
        # But we let it scan just in case you add Crypto symbols.

    # Check Positions
    positions = trade_client.get_all_positions()
    current_symbols = [p.symbol for p in positions]
    print(f"Current Positions: {len(current_symbols)}/{MAX_POSITIONS} {current_symbols}")

    if len(current_symbols) >= MAX_POSITIONS:
        print("Max positions reached.")
        return

    # Scan
    for symbol in SYMBOLS:
        if symbol in current_symbols: continue
            
        df = get_data(symbol)
        if df is None or df.empty: continue
        
        signal = analyze_market(df)
        if signal == 'BUY':
            current_price = df.iloc[-1]['close']
            execute_bracket_order(symbol, current_price)
            if len(trade_client.get_all_positions()) >= MAX_POSITIONS:
                break
                
    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run_trading_cycle()
