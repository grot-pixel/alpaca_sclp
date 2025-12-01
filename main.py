import alpaca.trading.client
import alpaca.data.historical
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
# Read user's custom environment variables
api_key = os.getenv('APCA_API_KEY_1')
api_secret = os.getenv('APCA_API_SECRET_1')
# base_url is read but not used for client init (SDK handles it)
base_url = os.getenv('APCA_BASE_URL_1')

# Basic check for authentication
if not api_key or not api_secret:
    raise ValueError("Missing APCA_API_KEY_1 or APCA_API_SECRET_1. Check your GitHub Secrets.")

# CRITICAL FIX: Determine paper/live mode based on the key type or URL.
if base_url:
    # Use base_url to determine paper/live if it was provided
    paper_mode = 'paper' in base_url
else:
    # Use default paper/live detection based on key type
    paper_mode = 'paper' in api_key.lower()

# Initialize the clients using the simple 'paper' flag. 
# This tells the SDK to use the correct data and trading URLs automatically, 
# resolving the "Not Found" error.
trade_client = TradingClient(api_key, api_secret, paper=paper_mode)
data_client = StockHistoricalDataClient(api_key, api_secret, paper=paper_mode)


def get_data(symbol):
    """Fetch recent market data for analysis using StockHistoricalDataClient."""
    try:
        # Fetch last 100 bars for calculation
        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute, 
            start=datetime.now(pytz.utc) - timedelta(hours=5),
            limit=100
        )
        bars = data_client.get_stock_bars(request_params)
        df = bars.df
        
        if df.empty: return None
        
        # Resample data to 5-minute bars for consistent strategy application
        df = df.droplevel(0) # Remove symbol index
        df = df.resample('5min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
            
        return df
    except Exception as e:
        # The "Not Found" error is caught here if the market is closed or URL is wrong.
        print(f"[{symbol}] Data fetch failed: {e}")
        return None

def analyze_market(df):
    """
    Aggressive Technical Analysis
    Returns: 'BUY' or None
    """
    if len(df) < 20: return None # Need enough data for BB/RSI

    # Calculate RSI
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # Calculate Bollinger Bands
    bb = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bb], axis=1)
    
    # Define columns dynamically from pandas_ta output
    lower_band = df[f'BBL_20_2.0']
    upper_band = df[f'BBU_20_2.0']

    current = df.iloc[-1]
    
    # STRATEGY 1: Oversold Reversal (Sniper Entry)
    # Price is below lower band AND RSI is oversold
    if current['close'] < current[lower_band.name] and current['RSI'] < config['SYSTEM']['RSI_OVERSOLD']:
        return 'BUY'

    # STRATEGY 2: Momentum Surge (Trend Following)
    # Price broke upper band AND RSI indicates strong but not exhausted momentum
    if current['close'] > current[upper_band.name] and \
       config['SYSTEM']['RSI_MOMENTUM_MIN'] < current['RSI'] < config['SYSTEM']['RSI_MOMENTUM_MAX']:
        return 'BUY'

    return None

def execute_bracket_order(symbol, price):
    """Submits a smart OTOCO (One-Triggers-One-Cancels-Other) order."""
    
    # Check liquidity/buying power
    account = trade_client.get_account()
    buying_power = float(account.regt_buying_power)
    
    if buying_power < USD_PER_TRADE:
        print(f"SKIPPING {symbol}: Insufficient buying power (${buying_power}).")
        return

    # Calculate Share Count
    qty = math.floor(USD_PER_TRADE / price)
    if qty < 1:
        print(f"SKIPPING {symbol}: Price too high for trade size.")
        return

    # Calculate Exits
    take_profit_price = round(price * (1 + TARGET_GAIN), 2)
    stop_loss_price = round(price * (1 - STOP_LOSS), 2)

    print(f" >> EXECUTING BUY: {symbol} x {qty} @ ${price}")
    print(f"    TARGET: ${take_profit_price} (+{TARGET_GAIN*100:.1f}%) | STOP: ${stop_loss_price} (-{STOP_LOSS*100:.1f}%)")

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
    print(f"--- AGGRESSIVE SCALPER SCAN STARTED: {datetime.now(pytz.utc)} ---")
    
    # Check Market Status
    try:
        clock = trade_client.get_clock()
        if not clock.is_open:
            print("Market Closed. (Note: Crypto markets may be open 24/7).")
    except Exception as e:
        print(f"Warning: Failed to retrieve market clock status: {e}")

    # Check Active Positions
    positions = trade_client.get_all_positions()
    current_symbols = [p.symbol for p in positions]
    print(f"Current Positions: {len(current_symbols)}/{MAX_POSITIONS} {current_symbols}")

    if len(current_symbols) >= MAX_POSITIONS:
        print("Max concurrent positions reached. Skipping new entries.")
        return

    # Scan Watchlist
    for symbol in SYMBOLS:
        if symbol in current_symbols:
            continue
            
        df = get_data(symbol)
        if df is None or df.empty: continue
        
        signal = analyze_market(df)
        
        if signal == 'BUY':
            current_price = df.iloc[-1]['close']
            print(f"SIGNAL DETECTED for {symbol}: {signal}")
            execute_bracket_order(symbol, current_price)
            
            # Re-check position count after a trade
            if len(trade_client.get_all_positions()) >= MAX_POSITIONS:
                break
        
    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    run_trading_cycle()
