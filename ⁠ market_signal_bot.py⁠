#!/usr/bin/env python3
"""
Market Signal Telegram Bot - Lightweight, Autonomous Trading Alert System
Optimized for free-tier hosting and continuous operation
"""

import os
import time
import logging
import threading
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json
import requests
from flask import Flask, jsonify
import telebot
from telebot import types
from telebot.util import update_types
import signal
import sys

# ==================== Configuration ====================
# Environment variables (set these in your hosting platform)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '')  # Free tier available
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))  # 5 minutes default
SIGNIFICANT_CHANGE_THRESHOLD = float(os.getenv('CHANGE_THRESHOLD', '1.0'))  # 1% default

# Assets to monitor (customizable)
ASSETS_TO_MONITOR = [
    'SPY',    # S&P 500 ETF
    'QQQ',    # Nasdaq ETF
    'DIA',    # Dow Jones ETF
    'BTC-USD', # Bitcoin
    'ETH-USD', # Ethereum
]

# ==================== Logging Setup ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# ==================== Flask Keep-Alive Server ====================
app = Flask(__name__)

@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        'status': 'alive',
        'bot': 'Market Signal Bot',
        'timestamp': datetime.now().isoformat(),
        'uptime': time.time() - START_TIME
    })

@app.route('/health')
def health():
    """Detailed health check"""
    return jsonify({
        'status': 'healthy',
        'monitored_assets': len(ASSETS_TO_MONITOR),
        'last_check': LAST_CHECK_TIME,
        'signals_sent': SIGNALS_SENT
    })

def run_flask():
    """Run Flask server in background thread for keep-alive"""
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==================== Market Data Handler ====================
class MarketDataHandler:
    """Handles market data fetching with fallback sources"""
    
    def __init__(self):
        self.cache = {}
        self.last_update = {}
        self.cache_timeout = 60  # seconds
        
    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price with caching and multiple fallback sources"""
        current_time = time.time()
        
        # Check cache first
        if symbol in self.cache and symbol in self.last_update:
            if current_time - self.last_update[symbol] < self.cache_timeout:
                return self.cache[symbol]
        
        # Try multiple data sources
        price = self._get_price_alpha_vantage(symbol)
        if price is None:
            price = self._get_price_yahoo(symbol)
        
        if price is not None:
            self.cache[symbol] = price
            self.last_update[symbol] = current_time
        
        return price
    
    def _get_price_alpha_vantage(self, symbol: str) -> Optional[float]:
        """Fetch price from Alpha Vantage (free tier)"""
        if not ALPHA_VANTAGE_API_KEY:
            return None
        
        try:
            # Map crypto symbols to Alpha Vantage format
            av_symbol = symbol.replace('-USD', '')
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'CURRENCY_EXCHANGE_RATE' if '-USD' in symbol else 'GLOBAL_QUOTE',
                'symbol': av_symbol,
                'apikey': ALPHA_VANTAGE_API_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'Global Quote' in data:
                return float(data['Global Quote']['05. price'])
            elif 'Realtime Currency Exchange Rate' in data:
                return float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
        except Exception as e:
            logger.warning(f"Alpha Vantage error for {symbol}: {e}")
        
        return None
    
    def _get_price_yahoo(self, symbol: str) -> Optional[float]:
        """Fetch price from Yahoo Finance (fallback)"""
        try:
            yahoo_symbol = symbol.replace('-USD', '-USD')
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
            params = {'interval': '1m', 'range': '1d'}
            
            response = requests.get(url, params=params, timeout=10,
                                   headers={'User-Agent': 'Mozilla/5.0'})
            data = response.json()
            
            if 'chart' in data and 'result' in data['chart']:
                result = data['chart']['result'][0]
                if 'meta' in result and 'regularMarketPrice' in result['meta']:
                    return float(result['meta']['regularMarketPrice'])
        except Exception as e:
            logger.warning(f"Yahoo Finance error for {symbol}: {e}")
        
        return None

# ==================== Signal Detection ====================
class SignalDetector:
    """Detects significant market movements"""
    
    def __init__(self, threshold: float):
        self.threshold = threshold
        self.baseline_prices = {}
        self.last_signal_time = {}
        self.signal_cooldown = 1800  # 30 minutes between signals for same asset
        
    def check_signals(self, current_prices: Dict[str, float]) -> list:
        """Check for significant price movements"""
        signals = []
        current_time = time.time()
        
        for symbol, price in current_prices.items():
            if price is None:
                continue
            
            # Initialize baseline if not exists
            if symbol not in self.baseline_prices:
                self.baseline_prices[symbol] = price
                continue
            
            # Calculate percentage change
            baseline = self.baseline_prices[symbol]
            if baseline == 0:
                continue
                
            percent_change = ((price - baseline) / baseline) * 100
            
            # Check if change exceeds threshold
            if abs(percent_change) >= self.threshold:
                # Check cooldown period
                if symbol in self.last_signal_time:
                    if current_time - self.last_signal_time[symbol] < self.signal_cooldown:
                        continue
                
                signal = {
                    'symbol': symbol,
                    'current_price': price,
                    'baseline_price': baseline,
                    'percent_change': percent_change,
                    'direction': 'up' if percent_change > 0 else 'down',
                    'timestamp': datetime.now().isoformat()
                }
                
                signals.append(signal)
                self.last_signal_time[symbol] = current_time
                self.baseline_prices[symbol] = price  # Reset baseline
        
        return signals

# ==================== Telegram Bot ====================
class MarketSignalBot:
    """Main Telegram bot class"""
    
    def __init__(self):
        if not TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        
        self.bot = telebot.TeleBot(TELEGRAM_TOKEN)
        self.market_data = MarketDataHandler()
        self.signal_detector = SignalDetector(SIGNIFICANT_CHANGE_THRESHOLD)
        self.is_running = True
        
        # Register handlers
        self.register_handlers()
        
        logger.info("Bot initialized successfully")
    
    def register_handlers(self):
        """Register Telegram command handlers"""
        
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            """Handle start/help commands"""
            welcome_text = (
                "🤖 *Market Signal Bot*\n\n"
                "I monitor market movements and alert you on significant changes.\n\n"
                "*Available commands:*\n"
                "/status - Check bot status\n"
                "/prices - Get current prices\n"
                "/threshold - Get/set alert threshold\n"
                "/pause - Pause alerts\n"
                "/resume - Resume alerts\n"
                "/help - Show this help message"
            )
            self.bot.reply_to(message, welcome_text, parse_mode='Markdown')
        
        @self.bot.message_handler(commands=['status'])
        def send_status(message):
            """Send bot status"""
            status_text = (
                f"✅ *Bot Status:* Running\n"
                f"📊 *Monitoring:* {len(ASSETS_TO_MONITOR)} assets\n"
                f"⚡ *Alert Threshold:* {SIGNIFICANT_CHANGE_THRESHOLD}%\n"
                f"⏱ *Check Interval:* {CHECK_INTERVAL} seconds\n"
                f"🕐 *Uptime:* {time.time() - START_TIME:.0f} seconds"
            )
            self.bot.reply_to(message, status_text, parse_mode='Markdown')
        
        @self.bot.message_handler(commands=['prices'])
        def send_prices(message):
            """Send current prices"""
            prices_text = "📈 *Current Prices:*\n\n"
            
            for symbol in ASSETS_TO_MONITOR:
                price = self.market_data.get_price(symbol)
                if price is not None:
                    prices_text += f"• {symbol}: ${price:,.2f}\n"
                else:
                    prices_text += f"• {symbol}: Unavailable\n"
            
            self.bot.reply_to(message, prices_text, parse_mode='Markdown')
        
        @self.bot.message_handler(func=lambda m: True)
        def echo_all(message):
            """Handle all other messages"""
            self.bot.reply_to(message, "Use /help to see available commands.")
    
    def send_signal_alert(self, signal: Dict[str, Any]):
        """Send signal alert to Telegram"""
        if not CHAT_ID:
            logger.warning("CHAT_ID not set, cannot send alert")
            return
        
        emoji = "📈" if signal['direction'] == 'up' else "📉"
        direction_color = "🟢" if signal['direction'] == 'up' else "🔴"
        
        alert_text = (
            f"{emoji} *SIGNIFICANT MARKET MOVE*\n\n"
            f"*Asset:* {signal['symbol']}\n"
            f"{direction_color} *Direction:* {signal['direction'].upper()}\n"
            f"*Change:* {signal['percent_change']:+.2f}%\n\n"
            f"*Current Price:* ${signal['current_price']:,.2f}\n"
            f"*Baseline Price:* ${signal['baseline_price']:,.2f}\n"
            f"*Time:* {signal['timestamp']}"
        )
        
        try:
            self.bot.send_message(CHAT_ID, alert_text, parse_mode='Markdown')
            logger.info(f"Signal alert sent for {signal['symbol']}")
            
            global SIGNALS_SENT
            SIGNALS_SENT += 1
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def monitor_market(self):
        """Main monitoring loop"""
        logger.info("Starting market monitoring...")
        
        while self.is_running:
            try:
                current_prices = {}
                for symbol in ASSETS_TO_MONITOR:
                    price = self.market_data.get_price(symbol)
                    current_prices[symbol] = price
                    logger.debug(f"{symbol}: {price}")
                
                signals = self.signal_detector.check_signals(current_prices)
                
                for signal in signals:
                    self.send_signal_alert(signal)
                
                global LAST_CHECK_TIME
                LAST_CHECK_TIME = datetime.now().isoformat()
                
                # Wait before next check
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                # Wait a bit longer on error to avoid rapid error loops
                time.sleep(60)
    
    def run(self):
        """Run the bot"""
        # Start Flask server in background
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Start market monitoring in background
        monitor_thread = threading.Thread(target=self.monitor_market, daemon=True)
        monitor_thread.start()
        
        # Start Telegram polling (main thread)
        logger.info("Starting Telegram bot polling...")
        while self.is_running:
            try:
                self.bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                time.sleep(15)

# ==================== Global Variables ====================
START_TIME = time.time()
LAST_CHECK_TIME = None
SIGNALS_SENT = 0

# ==================== Main Entry Point ====================
def main():
    """Main function"""
    try:
        # Validate environment
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
            sys.exit(1)
        
        # Initialize and run bot
        bot = MarketSignalBot()
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()