#!/usr/bin/env python3
"""
نظام التداول الذاتي التطور - الإصدار المتقدم
مع دعم الفراغات السعرية المؤسسية (FVG) وكتل الأوامر (Order Blocks)
Self-Evolving Trading System with Institutional Footprints
"""

import os
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('suhail_hunter')
import threading
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from flask import Flask, jsonify, request
import telebot
from telebot import types
from collections import deque
import warnings
warnings.filterwarnings('ignore')

# ==================== إعدادات النظام ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))
PORT = int(os.getenv('PORT', 8080))

ASSETS_TO_MONITOR = [
    'SPY', 'QQQ', 'IWM', 'DIA',
    'AAPL', 'MSFT', 'NVDA', 'TSLA',
    'BTC-USD', 'ETH-USD',
    'GLD', 'SLV',
]

# ==================== معلمات التطور الذاتي المتقدمة ====================
class AdaptiveParameters:
    """معلمات متطورة مع أوزان ديناميكية للمؤشرات"""
    def __init__(self):
        # معلمات السيولة والزخم
        self.rvol_threshold = float(os.getenv('RVOL_THRESHOLD', '2.0'))
        self.momentum_threshold = float(os.getenv('MOMENTUM_THRESHOLD', '0.5'))
        self.price_change_threshold = float(os.getenv('PRICE_CHANGE_THRESHOLD', '0.8'))
        
        # معلمات FVG و Order Blocks
        self.fvg_min_size = 0.001  # الحد الأدنى لحجم الفراغ (% من السعر)
        self.fvg_lookback = 50  # عدد الشموع للبحث عن FVG
        self.ob_lookback = 50  # عدد الشموع لتحديد Order Blocks
        self.fvg_fill_ratio_threshold = 0.5  # نسبة ملء الفراغ للاعتبار
        
        # أوزان ديناميكية للمؤشرات (تتطور ذاتياً)
        self.weight_rvol = 0.3
        self.weight_momentum = 0.2
        self.weight_rsi = 0.1
        self.weight_fvg = 0.25
        self.weight_order_block = 0.15
        
        # معلمات التعلم
        self.learning_rate = 0.1
        self.performance_window = 30
        self.min_confidence = 0.55
        self.confidence_threshold = 0.65
        
        # معلمات RSI
        self.rsi_oversold = float(os.getenv('RSI_OVERSOLD', '30'))
        self.rsi_overbought = float(os.getenv('RSI_OVERBOUGHT', '70'))
        
        # معلمات إضافية
        self.signal_cooldown = int(os.getenv('SIGNAL_COOLDOWN', '300'))
        self.max_position_holding = 7200  # ثواني (ساعتين)

# ==================== قاعدة البيانات المتطورة ====================
class AdvancedSignalDatabase:
    """قاعدة بيانات متطورة مع تتبع المؤشرات المؤسسية"""
    
    def __init__(self, db_path='advanced_signals.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """تهيئة قاعدة البيانات المتطورة"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # جدول الإشارات المتطور
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS advanced_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    -- مؤشرات السيولة
                    rvol REAL,
                    momentum REAL,
                    rsi REAL,
                    -- مؤشرات مؤسسية
                    fvg_present BOOLEAN,
                    fvg_size REAL,
                    fvg_type TEXT,
                    fvg_fill_ratio REAL,
                    order_block_present BOOLEAN,
                    order_block_type TEXT,
                    order_block_strength REAL,
                    -- الأوزان المستخدمة
                    weight_rvol REAL,
                    weight_momentum REAL,
                    weight_rsi REAL,
                    weight_fvg REAL,
                    weight_order_block REAL,
                    -- النتيجة
                    confidence REAL,
                    status TEXT DEFAULT 'open',
                    exit_price REAL,
                    exit_time TEXT,
                    pnl_percent REAL,
                    is_win BOOLEAN
                )
            ''')
            
            # جدول أداء المؤشرات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS indicator_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicator_name TEXT NOT NULL,
                    indicator_value TEXT,
                    signal_count INTEGER,
                    win_count INTEGER,
                    win_rate REAL,
                    avg_pnl REAL,
                    updated_at TEXT
                )
            ''')
            
            # جدول الأوزان المتطورة
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS adaptive_weights (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    weight_rvol REAL,
                    weight_momentum REAL,
                    weight_rsi REAL,
                    weight_fvg REAL,
                    weight_order_block REAL,
                    fvg_min_size REAL,
                    ob_lookback INTEGER,
                    last_updated TEXT
                )
            ''')
            
            # جدول تحليل FVG
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fvg_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    fvg_type TEXT,
                    fvg_size REAL,
                    fill_rate REAL,
                    success_rate REAL,
                    signal_count INTEGER,
                    updated_at TEXT
                )
            ''')
            
            conn.commit()
    
    def save_advanced_signal(self, signal_data: Dict[str, Any]) -> int:
        """حفظ إشارة متقدمة مع جميع المؤشرات"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO advanced_signals 
                (symbol, direction, entry_price, entry_time,
                 rvol, momentum, rsi,
                 fvg_present, fvg_size, fvg_type, fvg_fill_ratio,
                 order_block_present, order_block_type, order_block_strength,
                 weight_rvol, weight_momentum, weight_rsi, weight_fvg, weight_order_block,
                 confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal_data['symbol'],
                signal_data['direction'],
                signal_data['entry_price'],
                signal_data['entry_time'],
                signal_data.get('rvol', 0),
                signal_data.get('momentum', 0),
                signal_data.get('rsi', 0),
                signal_data.get('fvg_present', False),
                signal_data.get('fvg_size', 0),
                signal_data.get('fvg_type', 'none'),
                signal_data.get('fvg_fill_ratio', 0),
                signal_data.get('order_block_present', False),
                signal_data.get('order_block_type', 'none'),
                signal_data.get('order_block_strength', 0),
                signal_data.get('weight_rvol', 0),
                signal_data.get('weight_momentum', 0),
                signal_data.get('weight_rsi', 0),
                signal_data.get('weight_fvg', 0),
                signal_data.get('weight_order_block', 0),
                signal_data.get('confidence', 0)
            ))
            conn.commit()
            return cursor.lastrowid
    
    def update_signal_result(self, signal_id: int, exit_price: float, exit_time: str):
        """تحديث نتيجة الإشارة"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT entry_price, direction FROM advanced_signals WHERE id = ?', (signal_id,))
            result = cursor.fetchone()
            
            if result:
                entry_price, direction = result
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
                if direction == 'short':
                    pnl_percent = -pnl_percent
                
                is_win = pnl_percent > 0
                
                cursor.execute('''
                    UPDATE advanced_signals 
                    SET exit_price = ?, exit_time = ?, pnl_percent = ?, 
                        is_win = ?, status = 'closed'
                    WHERE id = ?
                ''', (exit_price, exit_time, pnl_percent, is_win, signal_id))
                
                conn.commit()
                return pnl_percent, is_win
        
        return None, None
    
    def get_closed_signals(self, limit=50):
        """جلب الإشارات المغلقة للتحليل"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM advanced_signals 
                WHERE status = 'closed' 
                ORDER BY exit_time DESC 
                LIMIT ?
            ''', (limit,))
            
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_open_signals(self):
        """جلب الإشارات المفتوحة"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM advanced_signals WHERE status = "open"')
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def update_indicator_performance(self, indicator_name: str, indicator_value: str, 
                                   is_win: bool, pnl: float):
        """تحديث أداء كل مؤشر على حدة"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # البحث عن الأداء الحالي
            cursor.execute('''
                SELECT signal_count, win_count FROM indicator_performance 
                WHERE indicator_name = ? AND indicator_value = ?
            ''', (indicator_name, indicator_value))
            
            result = cursor.fetchone()
            
            if result:
                signal_count, win_count = result
                signal_count += 1
                win_count += 1 if is_win else 0
                win_rate = (win_count / signal_count) * 100
                
                cursor.execute('''
                    UPDATE indicator_performance 
                    SET signal_count = ?, win_count = ?, win_rate = ?, 
                        avg_pnl = (avg_pnl * (? - 1) + ?) / ?, updated_at = ?
                    WHERE indicator_name = ? AND indicator_value = ?
                ''', (signal_count, win_count, win_rate, signal_count, pnl, signal_count,
                      datetime.now().isoformat(), indicator_name, indicator_value))
            else:
                cursor.execute('''
                    INSERT INTO indicator_performance 
                    (indicator_name, indicator_value, signal_count, win_count, win_rate, avg_pnl, updated_at)
                    VALUES (?, ?, 1, ?, ?, ?, ?)
                ''', (indicator_name, indicator_value, 1 if is_win else 0,
                      100 if is_win else 0, pnl, datetime.now().isoformat()))
            
            conn.commit()
    
    def load_adaptive_weights(self):
        """تحميل الأوزان المتطورة"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM adaptive_weights WHERE id = 1')
            result = cursor.fetchone()
            
            if result:
                return {
                    'weight_rvol': result[1],
                    'weight_momentum': result[2],
                    'weight_rsi': result[3],
                    'weight_fvg': result[4],
                    'weight_order_block': result[5],
                    'fvg_min_size': result[6],
                    'ob_lookback': result[7]
                }
        return None
    
    def save_adaptive_weights(self, params: AdaptiveParameters):
        """حفظ الأوزان المتطورة"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO adaptive_weights 
                (id, weight_rvol, weight_momentum, weight_rsi, weight_fvg, weight_order_block,
                 fvg_min_size, ob_lookback, last_updated)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                params.weight_rvol,
                params.weight_momentum,
                params.weight_rsi,
                params.weight_fvg,
                params.weight_order_block,
                params.fvg_min_size,
                params.ob_lookback,
                datetime.now().isoformat()
            ))
            conn.commit()
    
    def analyze_fvg_performance(self):
        """تحليل أداء FVG حسب النوع والحجم"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # تحليل حسب نوع FVG
            cursor.execute('''
                SELECT fvg_type, 
                       COUNT(*) as count,
                       SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                       AVG(pnl_percent) as avg_pnl
                FROM advanced_signals 
                WHERE status = 'closed' AND fvg_present = 1
                GROUP BY fvg_type
            ''')
            
            fvg_types_analysis = cursor.fetchall()
            
            # تحليل حسب حجم FVG
            cursor.execute('''
                SELECT 
                    CASE 
                        WHEN fvg_size < 0.002 THEN 'small'
                        WHEN fvg_size < 0.005 THEN 'medium'
                        ELSE 'large'
                    END as size_category,
                    COUNT(*) as count,
                    SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                    AVG(pnl_percent) as avg_pnl
                FROM advanced_signals 
                WHERE status = 'closed' AND fvg_present = 1
                GROUP BY size_category
            ''')
            
            fvg_size_analysis = cursor.fetchall()
            
            return {
                'types': fvg_types_analysis,
                'sizes': fvg_size_analysis
            }

# ==================== كاشف الفراغات السعرية المؤسسية ====================
class InstitutionalFootprintDetector:
    """كاشف متطور للفراغات السعرية وكتل الأوامر"""
    
    def __init__(self, params: AdaptiveParameters):
        self.params = params
        self.fvg_cache = {}
        self.ob_cache = {}
        self.cache_timeout = 300  # 5 دقائق
    
    def detect_fvg(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """كشف الفراغات السعرية المؤسسية Fair Value Gaps"""
        if data.empty or len(data) < 3:
            return []
        
        fvgs = []
        lookback = min(self.params.fvg_lookback, len(data) - 3)
        
        for i in range(len(data) - lookback, len(data) - 2):
            # Bullish FVG: Low[i+2] > High[i]
            if data['Low'].iloc[i + 2] > data['High'].iloc[i]:
                gap_top = data['Low'].iloc[i + 2]
                gap_bottom = data['High'].iloc[i]
                gap_size = (gap_top - gap_bottom) / gap_bottom
                
                if gap_size >= self.params.fvg_min_size:
                    fvgs.append({
                        'type': 'bullish',
                        'top': gap_top,
                        'bottom': gap_bottom,
                        'size': gap_size,
                        'index': i + 2,
                        'time': data.index[i + 2]
                    })
            
            # Bearish FVG: High[i+2] < Low[i]
            elif data['High'].iloc[i + 2] < data['Low'].iloc[i]:
                gap_top = data['Low'].iloc[i]
                gap_bottom = data['High'].iloc[i + 2]
                gap_size = (gap_top - gap_bottom) / gap_top
                
                if gap_size >= self.params.fvg_min_size:
                    fvgs.append({
                        'type': 'bearish',
                        'top': gap_top,
                        'bottom': gap_bottom,
                        'size': gap_size,
                        'index': i + 2,
                        'time': data.index[i + 2]
                    })
        
        return fvgs
    
    def detect_order_blocks(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """كشف كتل الأوامر Order Blocks"""
        if data.empty or len(data) < 10:
            return []
        
        order_blocks = []
        lookback = min(self.params.ob_lookback, len(data) - 5)
        
        for i in range(len(data) - lookback, len(data) - 4):
            # البحث عن كتلة أوامر صاعدة (آخر شمعة هابطة قبل حركة صاعدة قوية)
            if (data['Close'].iloc[i] < data['Open'].iloc[i] and  # شمعة هابطة
                data['Close'].iloc[i + 1] > data['Open'].iloc[i + 1] and  # شمعة صاعدة
                data['Close'].iloc[i + 2] > data['High'].iloc[i]):  # كسر قوي
                
                ob_strength = (data['Close'].iloc[i + 2] - data['High'].iloc[i]) / data['High'].iloc[i]
                
                order_blocks.append({
                    'type': 'bullish',
                    'top': data['High'].iloc[i],
                    'bottom': data['Low'].iloc[i],
                    'strength': ob_strength,
                    'index': i,
                    'time': data.index[i]
                })
            
            # البحث عن كتلة أوامر هابطة (آخر شمعة صاعدة قبل حركة هابطة قوية)
            elif (data['Close'].iloc[i] > data['Open'].iloc[i] and  # شمعة صاعدة
                  data['Close'].iloc[i + 1] < data['Open'].iloc[i + 1] and  # شمعة هابطة
                  data['Close'].iloc[i + 2] < data['Low'].iloc[i]):  # كسر قوي
                
                ob_strength = (data['Low'].iloc[i] - data['Close'].iloc[i + 2]) / data['Low'].iloc[i]
                
                order_blocks.append({
                    'type': 'bearish',
                    'top': data['High'].iloc[i],
                    'bottom': data['Low'].iloc[i],
                    'strength': ob_strength,
                    'index': i,
                    'time': data.index[i]
                })
        
        return order_blocks
    
    def analyze_institutional_context(self, symbol: str, data: pd.DataFrame) -> Dict[str, Any]:
        """تحليل السياق المؤسسي الكامل"""
        cache_key = f"{symbol}_{data.index[-1] if not data.empty else 'empty'}"
        
        # استخدام التخزين المؤقت
        if cache_key in self.fvg_cache and cache_key in self.ob_cache:
            current_time = time.time()
            if current_time - self.fvg_cache[cache_key]['timestamp'] < self.cache_timeout:
                return {
                    'fvgs': self.fvg_cache[cache_key]['data'],
                    'order_blocks': self.ob_cache[cache_key]['data'],
                    'nearest_fvg': self.find_nearest_fvg(data['Close'].iloc[-1], self.fvg_cache[cache_key]['data']),
                    'nearest_ob': self.find_nearest_ob(data['Close'].iloc[-1], self.ob_cache[cache_key]['data'])
                }
        
        # كشف الفراغات وكتل الأوامر
        fvgs = self.detect_fvg(data)
        order_blocks = self.detect_order_blocks(data)
        
        # تخزين في الذاكرة المؤقتة
        current_time = time.time()
        self.fvg_cache[cache_key] = {'data': fvgs, 'timestamp': current_time}
        self.ob_cache[cache_key] = {'data': order_blocks, 'timestamp': current_time}
        
        return {
            'fvgs': fvgs,
            'order_blocks': order_blocks,
            'nearest_fvg': self.find_nearest_fvg(data['Close'].iloc[-1], fvgs),
            'nearest_ob': self.find_nearest_ob(data['Close'].iloc[-1], order_blocks)
        }
    
    def find_nearest_fvg(self, current_price: float, fvgs: List[Dict]) -> Optional[Dict]:
        """البحث عن أقرب FVG للسعر الحالي"""
        if not fvgs:
            return None
        
        nearest = None
        min_distance = float('inf')
        
        for fvg in fvgs:
            # حساب المسافة
            if fvg['type'] == 'bullish':
                distance = abs(current_price - fvg['bottom'])
            else:
                distance = abs(current_price - fvg['top'])
            
            if distance < min_distance:
                min_distance = distance
                nearest = fvg
        
        return nearest
    
    def find_nearest_ob(self, current_price: float, order_blocks: List[Dict]) -> Optional[Dict]:
        """البحث عن أقرب Order Block للسعر الحالي"""
        if not order_blocks:
            return None
        
        nearest = None
        min_distance = float('inf')
        
        for ob in order_blocks:
            ob_mid = (ob['top'] + ob['bottom']) / 2
            distance = abs(current_price - ob_mid)
            
            if distance < min_distance:
                min_distance = distance
                nearest = ob
        
        return nearest
    
    def calculate_fvg_fill_ratio(self, current_price: float, fvg: Dict) -> float:
        """حساب نسبة ملء الفراغ السعري"""
        if not fvg:
            return 0.0
        
        gap_size = fvg['top'] - fvg['bottom']
        if gap_size == 0:
            return 0.0
        
        if fvg['type'] == 'bullish':
            # نسبة الملء من الأسفل
            if current_price <= fvg['bottom']:
                return 0.0
            elif current_price >= fvg['top']:
                return 1.0
            else:
                return (current_price - fvg['bottom']) / gap_size
        else:
            # نسبة الملء من الأعلى
            if current_price >= fvg['top']:
                return 0.0
            elif current_price <= fvg['bottom']:
                return 1.0
            else:
                return (fvg['top'] - current_price) / gap_size

# ==================== المحلل المتكامل المتطور ====================
class IntegratedMarketAnalyzer:
    """محلل متكامل يجمع جميع المؤشرات مع الأوزان الديناميكية"""
    
    def __init__(self, params: AdaptiveParameters):
        self.params = params
        self.price_cache = {}
        self.last_update = {}
        self.institutional_detector = InstitutionalFootprintDetector(params)
    
    def get_market_data(self, symbol: str, period: str = '5d', interval: str = '5m') -> pd.DataFrame:
        """جلب بيانات السوق مع التخزين المؤقت"""
        cache_key = f"{symbol}_{period}_{interval}"
        current_time = time.time()
        
        if cache_key in self.last_update:
            if current_time - self.last_update[cache_key] < 30:
                return self.price_cache.get(cache_key)
        
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=interval)
            
            if not data.empty:
                self.price_cache[cache_key] = data
                self.last_update[cache_key] = current_time
                return data
                
        except Exception as e:
            logger.warning(f"خطأ في جلب بيانات {symbol}: {e}")
            
            try:
                if '-USD' in symbol:
                    crypto_symbol = symbol.replace('-USD', '')
                    url = f"https://api.coingecko.com/api/v3/coins/{crypto_symbol}/market_chart"
                    params = {'vs_currency': 'usd', 'days': '5', 'interval': 'minutely'}
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        prices = data.get('prices', [])
                        volumes = data.get('total_volumes', [])
                        
                        df = pd.DataFrame({
                            'Open': [p[1] for p in prices],
                            'High': [p[1] * 1.001 for p in prices],
                            'Low': [p[1] * 0.999 for p in prices],
                            'Close': [p[1] for p in prices],
                            'Volume': [v[1] for v in volumes]
                        }, index=[datetime.fromtimestamp(p[0]/1000) for p in prices])
                        
                        self.price_cache[cache_key] = df
                        self.last_update[cache_key] = current_time
                        return df
            except Exception as e2:
                logger.warning(f"خطأ في المصدر البديل {symbol}: {e2}")
        
        return pd.DataFrame()
    
    def calculate_rvol(self, data: pd.DataFrame, lookback: int = 20) -> float:
        """حساب الحجم النسبي"""
        if data.empty or 'Volume' not in data.columns or len(data) < lookback:
            return 0.0
        
        current_volume = data['Volume'].iloc[-1]
        avg_volume = data['Volume'].iloc[-lookback:-1].mean()
        
        if avg_volume == 0:
            return 0.0
        
        return current_volume / avg_volume
    
    def calculate_momentum(self, data: pd.DataFrame, period: int = 10) -> float:
        """حساب الزخم"""
        if data.empty or 'Close' not in data.columns or len(data) < period:
            return 0.0
        
        current_price = data['Close'].iloc[-1]
        past_price = data['Close'].iloc[-period]
        
        if past_price == 0:
            return 0.0
        
        return ((current_price - past_price) / past_price) * 100
    
    def calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> float:
        """حساب RSI"""
        if data.empty or 'Close' not in data.columns or len(data) < period + 1:
            return 50.0
        
        closes = data['Close'].values
        deltas = np.diff(closes)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        """تحليل شامل متكامل"""
        data = self.get_market_data(symbol)
        
        if data.empty:
            return {'symbol': symbol, 'available': False, 'error': 'لا توجد بيانات'}
        
        current_price = data['Close'].iloc[-1]
        
        # حساب المؤشرات الأساسية
        rvol = self.calculate_rvol(data)
        momentum = self.calculate_momentum(data)
        rsi = self.calculate_rsi(data)
        
        # كشف المؤشرات المؤسسية
        institutional_context = self.institutional_detector.analyze_institutional_context(symbol, data)
        nearest_fvg = institutional_context.get('nearest_fvg')
        nearest_ob = institutional_context.get('nearest_ob')
        
        # حساب ملء الفراغ
        fvg_fill_ratio = self.institutional_detector.calculate_fvg_fill_ratio(current_price, nearest_fvg) if nearest_fvg else 0
        
        # حساب الثقة المتكاملة مع الأوزان الديناميكية
        confidence = self.calculate_integrated_confidence(
            rvol, momentum, rsi, nearest_fvg, nearest_ob, fvg_fill_ratio
        )
        
        return {
            'symbol': symbol,
            'available': True,
            'current_price': current_price,
            'rvol': rvol,
            'momentum': momentum,
            'rsi': rsi,
            'fvg_present': nearest_fvg is not None,
            'fvg': nearest_fvg,
            'fvg_fill_ratio': fvg_fill_ratio,
            'order_block_present': nearest_ob is not None,
            'order_block': nearest_ob,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat()
        }
    
    def calculate_integrated_confidence(self, rvol: float, momentum: float, rsi: float,
                                       fvg: Optional[Dict], ob: Optional[Dict], 
                                       fvg_fill_ratio: float) -> float:
        """حساب الثقة المتكاملة باستخدام الأوزان الديناميكية"""
        confidence = 0.0
        total_weight = 0.0
        
        # مساهمة RVOL
        if rvol >= self.params.rvol_threshold:
            rvol_score = min(1.0, rvol / self.params.rvol_threshold)
            confidence += self.params.weight_rvol * rvol_score
            total_weight += self.params.weight_rvol
        
        # مساهمة الزخم
        if abs(momentum) >= self.params.momentum_threshold:
            momentum_score = min(1.0, abs(momentum) / (self.params.momentum_threshold * 2))
            confidence += self.params.weight_momentum * momentum_score
            total_weight += self.params.weight_momentum
        
        # مساهمة RSI
        if rsi <= self.params.rsi_oversold or rsi >= self.params.rsi_overbought:
            rsi_score = 1.0
            confidence += self.params.weight_rsi * rsi_score
            total_weight += self.params.weight_rsi
        
        # مساهمة FVG
        if fvg and fvg_fill_ratio < self.params.fvg_fill_ratio_threshold:
            fvg_score = 1.0 - fvg_fill_ratio
            confidence += self.params.weight_fvg * fvg_score
            total_weight += self.params.weight_fvg
        
        # مساهمة Order Block
        if ob and ob.get('strength', 0) > 0.001:
            ob_score = min(1.0, ob['strength'] * 10)
            confidence += self.params.weight_order_block * ob_score
            total_weight += self.params.weight_order_block
        
        # تطبيع الثقة
        if total_weight > 0:
            confidence = confidence / total_weight
        
        return min(confidence, 1.0)
    
    def generate_signal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """توليد إشارة متطورة"""
        if not analysis.get('available', False):
            return None
        
        confidence = analysis['confidence']
        if confidence < self.params.confidence_threshold:
            return None
        
        # تحديد الاتجاه بناءً على جميع المؤشرات
        direction = None
        
        # دمج إشارات الاتجاه
        bullish_signals = 0
        bearish_signals = 0
        
        if analysis['momentum'] > 0:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if analysis['fvg_present'] and analysis['fvg']['type'] == 'bullish':
            bullish_signals += 1
        elif analysis['fvg_present'] and analysis['fvg']['type'] == 'bearish':
            bearish_signals += 1
        
        if analysis['order_block_present'] and analysis['order_block']['type'] == 'bullish':
            bullish_signals += 1
        elif analysis['order_block_present'] and analysis['order_block']['type'] == 'bearish':
            bearish_signals += 1
        
        # قرار الاتجاه
        if bullish_signals > bearish_signals and analysis['rsi'] < self.params.rsi_overbought:
            direction = 'long'
        elif bearish_signals > bullish_signals and analysis['rsi'] > self.params.rsi_oversold:
            direction = 'short'
        
        if direction is None:
            return None
        
        return {
            'symbol': analysis['symbol'],
            'direction': direction,
            'entry_price': analysis['current_price'],
            'entry_time': analysis['timestamp'],
            'rvol': analysis['rvol'],
            'momentum': analysis['momentum'],
            'rsi': analysis['rsi'],
            'fvg_present': analysis['fvg_present'],
            'fvg_size': analysis['fvg']['size'] if analysis['fvg'] else 0,
            'fvg_type': analysis['fvg']['type'] if analysis['fvg'] else 'none',
            'fvg_fill_ratio': analysis['fvg_fill_ratio'],
            'order_block_present': analysis['order_block_present'],
            'order_block_type': analysis['order_block']['type'] if analysis['order_block'] else 'none',
            'order_block_strength': analysis['order_block']['strength'] if analysis['order_block'] else 0,
            'weight_rvol': self.params.weight_rvol,
            'weight_momentum': self.params.weight_momentum,
            'weight_rsi': self.params.weight_rsi,
            'weight_fvg': self.params.weight_fvg,
            'weight_order_block': self.params.weight_order_block,
            'confidence': confidence
        }

# ==================== نظام التعلم الذاتي المتطور ====================
class AdaptiveLearningSystem:
    """نظام تعلم ذاتي متطور يقيم ويطور جميع المؤشرات"""
    
    def __init__(self, db: AdvancedSignalDatabase, params: AdaptiveParameters):
        self.db = db
        self.params = params
        self.last_evaluation_time = time.time()
        self.evaluation_interval = 3600  # ساعة
    
    def evaluate_and_adapt(self):
        """تقييم الأداء وتكييف النظام"""
        closed_signals = self.db.get_closed_signals(self.params.performance_window)
        
        if len(closed_signals) < 10:
            logger.info("لا توجد إشارات كافية للتقييم (أقل من 10)")
            return
        
        total_signals = len(closed_signals)
        wins = sum(1 for s in closed_signals if s.get('is_win'))
        win_rate = (wins / total_signals) * 100
        
        pnls = [s.get('pnl_percent', 0) for s in closed_signals if s.get('pnl_percent') is not None]
        avg_pnl = np.mean(pnls) if pnls else 0
        
        logger.info(f"تقييم الأداء: {total_signals} إشارة، نسبة النجاح: {win_rate:.1f}%، متوسط الربح: {avg_pnl:.2f}%")
        
        # تحليل أداء كل مؤشر على حدة
        self.analyze_indicator_performance(closed_signals)
        
        # تحليل أداء FVG
        fvg_performance = self.db.analyze_fvg_performance()
        self.adapt_fvg_parameters(fvg_performance, closed_signals)
        
        # تعديل الأوزان
        self.adjust_weights(closed_signals, win_rate, avg_pnl)
        
        # حفظ الأوزان المحدثة
        self.db.save_adaptive_weights(self.params)
        
        logger.info(f"الأوزان المحدثة: RVOL={self.params.weight_rvol:.2f}, "
                   f"زخم={self.params.weight_momentum:.2f}, "
                   f"RSI={self.params.weight_rsi:.2f}, "
                   f"FVG={self.params.weight_fvg:.2f}, "
                   f"OB={self.params.weight_order_block:.2f}")
    
    def analyze_indicator_performance(self, signals: List[Dict]):
        """تحليل أداء كل مؤشر"""
        indicator_stats = {}
        
        for signal in signals:
            is_win = signal.get('is_win', False)
            pnl = signal.get('pnl_percent', 0)
            
            # RVOL performance
            if signal.get('rvol', 0) >= self.params.rvol_threshold:
                self.db.update_indicator_performance('RVOL', 'high', is_win, pnl)
            else:
                self.db.update_indicator_performance('RVOL', 'low', is_win, pnl)
            
            # Momentum performance
            if abs(signal.get('momentum', 0)) >= self.params.momentum_threshold:
                self.db.update_indicator_performance('Momentum', 'strong', is_win, pnl)
            else:
                self.db.update_indicator_performance('Momentum', 'weak', is_win, pnl)
            
            # FVG performance
            if signal.get('fvg_present', False):
                fvg_type = signal.get('fvg_type', 'none')
                self.db.update_indicator_performance('FVG', fvg_type, is_win, pnl)
            
            # Order Block performance
            if signal.get('order_block_present', False):
                ob_type = signal.get('order_block_type', 'none')
                self.db.update_indicator_performance('OB', ob_type, is_win, pnl)
    
    def adapt_fvg_parameters(self, fvg_performance: Dict, signals: List[Dict]):
        """تكييف معلمات FVG بناءً على الأداء"""
        # تحليل نجاح FVG حسب النوع
        fvg_signals = [s for s in signals if s.get('fvg_present', False)]
        
        if len(fvg_signals) < 5:
            return
        
        fvg_wins = sum(1 for s in fvg_signals if s.get('is_win', False))
        fvg_win_rate = (fvg_wins / len(fvg_signals)) * 100
        
        # إذا كانت FVG تؤدي بشكل جيد، نزيد وزنها
        if fvg_win_rate > 60:
            self.params.weight_fvg = min(0.4, self.params.weight_fvg + self.params.learning_rate)
            logger.info(f"زيادة وزن FVG إلى {self.params.weight_fvg:.2f} (نسبة النجاح: {fvg_win_rate:.1f}%)")
        elif fvg_win_rate < 45:
            self.params.weight_fvg = max(0.1, self.params.weight_fvg - self.params.learning_rate)
            logger.info(f"تقليل وزن FVG إلى {self.params.weight_fvg:.2f} (نسبة النجاح: {fvg_win_rate:.1f}%)")
        
        # تعديل حجم الفراغ الأدنى بناءً على الأداء
        large_fvgs = [s for s in fvg_signals if s.get('fvg_size', 0) > 0.005]
        small_fvgs = [s for s in fvg_signals if s.get('fvg_size', 0) <= 0.005]
        
        if len(large_fvgs) >= 3:
            large_win_rate = sum(1 for s in large_fvgs if s.get('is_win', False)) / len(large_fvgs) * 100
            if large_win_rate > 65:
                self.params.fvg_min_size = min(0.003, self.params.fvg_min_size + 0.0002)
                logger.info(f"زيادة الحد الأدنى لحجم FVG إلى {self.params.fvg_min_size:.4f}")
    
    def adjust_weights(self, signals: List[Dict], win_rate: float, avg_pnl: float):
        """تعديل الأوزان الديناميكية"""
        # حساب أداء كل مؤشر
        indicator_performance = {}
        
        for signal in signals:
            is_win = signal.get('is_win', False)
            
            # RVOL
            if signal.get('rvol', 0) >= self.params.rvol_threshold:
                indicator_performance.setdefault('rvol', []).append(is_win)
            
            # Momentum
            if abs(signal.get('momentum', 0)) >= self.params.momentum_threshold:
                indicator_performance.setdefault('momentum', []).append(is_win)
            
            # RSI
            if signal.get('rsi', 0) <= self.params.rsi_oversold or signal.get('rsi', 0) >= self.params.rsi_overbought:
                indicator_performance.setdefault('rsi', []).append(is_win)
            
            # FVG
            if signal.get('fvg_present', False):
                indicator_performance.setdefault('fvg', []).append(is_win)
            
            # Order Block
            if signal.get('order_block_present', False):
                indicator_performance.setdefault('ob', []).append(is_win)
        
        # تحديث الأوزان بناءً على الأداء
        total_weight = 0
        for indicator, results in indicator_performance.items():
            if len(results) >= 3:  # نحتاج على الأقل 3 نتائج
                indicator_win_rate = sum(results) / len(results) * 100
                
                # تعديل الوزن بناءً على الأداء
                if indicator_win_rate > 60:
                    # أداء جيد - زيادة الوزن
                    current_weight = getattr(self.params, f'weight_{indicator}')
                    new_weight = min(0.4, current_weight + self.params.learning_rate)
                    setattr(self.params, f'weight_{indicator}', new_weight)
                elif indicator_win_rate < 45:
                    # أداء ضعيف - تقليل الوزن
                    current_weight = getattr(self.params, f'weight_{indicator}')
                    new_weight = max(0.05, current_weight - self.params.learning_rate)
                    setattr(self.params, f'weight_{indicator}', new_weight)
                
                total_weight += getattr(self.params, f'weight_{indicator}')
        
        # تطبيع الأوزان
        if total_weight > 0:
            self.params.weight_rvol = self.params.weight_rvol / total_weight
            self.params.weight_momentum = self.params.weight_momentum / total_weight
            self.params.weight_rsi = self.params.weight_rsi / total_weight
            self.params.weight_fvg = self.params.weight_fvg / total_weight
            self.params.weight_order_block = self.params.weight_order_block / total_weight
    
    def close_old_signals(self, analyzer: IntegratedMarketAnalyzer):
        """إغلاق الإشارات القديمة"""
        open_signals = self.db.get_open_signals()
        
        for signal in open_signals:
            entry_time = datetime.fromisoformat(signal['entry_time'])
            current_time = datetime.now()
            
            if (current_time - entry_time).total_seconds() > self.params.max_position_holding:
                analysis = analyzer.analyze_symbol(signal['symbol'])
                
                if analysis.get('available', False):
                    pnl, is_win = self.db.update_signal_result(
                        signal['id'],
                        analysis['current_price'],
                        current_time.isoformat()
                    )
                    
                    logger.info(f"إغلاق إشارة {signal['symbol']}: {'ربح' if is_win else 'خسارة'} {pnl:.2f}%")
    
    def run_evaluation_loop(self, analyzer: IntegratedMarketAnalyzer):
        """حلقة التقييم المستمر"""
        while True:
            try:
                self.close_old_signals(analyzer)
                self.evaluate_and_adapt()
                time.sleep(self.evaluation_interval)
            except Exception as e:
                logger.error(f"خطأ في حلقة التقييم: {e}")
                time.sleep(300)

# ==================== بوت التليجرام المتطور ====================
class EvolutionaryTradingBot:
    """البوت الرئيسي المتطور"""
    
    def __init__(self):
        if not TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN مطلوب")
        
        self.bot = telebot.TeleBot(TELEGRAM_TOKEN)
        self.params = AdaptiveParameters()
        self.db = AdvancedSignalDatabase()
        self.analyzer = IntegratedMarketAnalyzer(self.params)
        self.learning_system = AdaptiveLearningSystem(self.db, self.params)
        self.is_running = True
        self.last_signal_time = {}
        self.signals_sent = 0
        
        # تحميل الأوزان المحفوظة
        saved_weights = self.db.load_adaptive_weights()
        if saved_weights:
            self.params.weight_rvol = saved_weights['weight_rvol']
            self.params.weight_momentum = saved_weights['weight_momentum']
            self.params.weight_rsi = saved_weights['weight_rsi']
            self.params.weight_fvg = saved_weights['weight_fvg']
            self.params.weight_order_block = saved_weights['weight_order_block']
            self.params.fvg_min_size = saved_weights['fvg_min_size']
            self.params.ob_lookback = saved_weights['ob_lookback']
            logger.info("تم تحميل الأوزان المتطورة")
        
        self.register_handlers()
        logger.info("تم تهيئة البوت التطوري بنجاح")
    
    def register_handlers(self):
        """تسجيل معالجات الأوامر"""
        
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            welcome_text = (
                "🚀 *نظام التداول الذاتي التطور المتقدم*\n\n"
                "نظام ذكي يدمج السيولة والزخم مع البصمات المؤسسية\n\n"
                "*الأوامر:*\n"
                "/status - حالة النظام\n"
                "/weights - الأوزان الحالية\n"
                "/fvg_analysis - تحليل FVG\n"
                "/performance - أداء النظام\n"
                "/analyze - تحليل فوري\n"
                "/help - المساعدة"
            )
            self.bot.reply_to(message, welcome_text, parse_mode='Markdown')
        
        @self.bot.message_handler(commands=['status'])
        def send_status(message):
            status_text = (
                f"✅ *حالة النظام:* نشط\n"
                f"📊 *الأصول:* {len(ASSETS_TO_MONITOR)}\n"
                f"💡 *الثقة المطلوبة:* {self.params.confidence_threshold:.0%}\n\n"
                f"*الأوزان الديناميكية:*\n"
                f"RVOL: {self.params.weight_rvol:.2f}\n"
                f"الزخم: {self.params.weight_momentum:.2f}\n"
                f"RSI: {self.params.weight_rsi:.2f}\n"
                f"FVG: {self.params.weight_fvg:.2f}\n"
                f"Order Blocks: {self.params.weight_order_block:.2f}"
            )
            self.bot.reply_to(message, status_text, parse_mode='Markdown')
        
        @self.bot.message_handler(commands=['weights'])
        def send_weights(message):
            weights_text = (
                f"⚖️ *الأوزان الديناميكية الحالية:*\n\n"
                f"RVOL: {self.params.weight_rvol:.3f}\n"
                f"Momentum: {self.params.weight_momentum:.3f}\n"
                f"RSI: {self.params.weight_rsi:.3f}\n"
                f"FVG: {self.params.weight_fvg:.3f}\n"
                f"Order Blocks: {self.params.weight_order_block:.3f}\n\n"
                f"*معلمات FVG:*\n"
                f"الحد الأدنى للحجم: {self.params.fvg_min_size:.4f}\n"
                f"فترة البحث: {self.params.fvg_lookback} شمعة"
            )
            self.bot.reply_to(message, weights_text, parse_mode='Markdown')
        
        @self.bot.message_handler(commands=['fvg_analysis'])
        def send_fvg_analysis(message):
            fvg_perf = self.db.analyze_fvg_performance()
            
            if not fvg_perf['types'] and not fvg_perf['sizes']:
                self.bot.reply_to(message, "لا توجد بيانات FVG كافية للتحليل.")
                return
            
            analysis_text = "📊 *تحليل أداء FVG:*\n\n"
            
            if fvg_perf['types']:
                analysis_text += "*حسب النوع:*\n"
                for row in fvg_perf['types']:
                    fvg_type, count, wins, avg_pnl = row
                    win_rate = (wins / count * 100) if count > 0 else 0
                    analysis_text += f"• {fvg_type}: {win_rate:.0f}% نجاح ({count} إشارة, PnL: {avg_pnl:.2f}%)\n"
            
            if fvg_perf['sizes']:
                analysis_text += "\n*حسب الحجم:*\n"
                for row in fvg_perf['sizes']:
                    size, count, wins, avg_pnl = row
                    win_rate = (wins / count * 100) if count > 0 else 0
                    analysis_text += f"• {size}: {win_rate:.0f}% نجاح ({count} إشارة, PnL: {avg_pnl:.2f}%)\n"
            
            self.bot.reply_to(message, analysis_text, parse_mode='Markdown')
        
        @self.bot.message_handler(commands=['analyze'])
        def send_analysis(message):
            analysis_text = "🔍 *تحليل متكامل:*\n\n"
            
            for symbol in ASSETS_TO_MONITOR[:5]:
                analysis = self.analyzer.analyze_symbol(symbol)
                if analysis.get('available', False):
                    fvg_info = "نعم" if analysis['fvg_present'] else "لا"
                    ob_info = "نعم" if analysis['order_block_present'] else "لا"
                    
                    analysis_text += (
                        f"*{symbol}:*\n"
                        f"السعر: ${analysis['current_price']:.2f}\n"
                        f"RVOL: {analysis['rvol']:.2f}x\n"
                        f"الزخم: {analysis['momentum']:.2f}%\n"
                        f"RSI: {analysis['rsi']:.1f}\n"
                        f"FVG: {fvg_info}\n"
                        f"Order Block: {ob_info}\n"
                        f"الثقة: {analysis['confidence']:.0%}\n\n"
                    )
            
            self.bot.reply_to(message, analysis_text, parse_mode='Markdown')
    
    def send_signal_alert(self, signal: Dict[str, Any]):
        """إرسال تنبيه الإشارة المتطور"""
        if not CHAT_ID:
            return
        
        emoji = "🟢" if signal['direction'] == 'long' else "🔴"
        direction_text = "شراء" if signal['direction'] == 'long' else "بيع"
        
        # إضافة معلومات FVG و Order Block
        institutional_info = ""
        if signal.get('fvg_present', False):
            institutional_info += f"\n📐 *FVG:* {signal.get('fvg_type', 'unknown')} (حجم: {signal.get('fvg_size', 0):.4f})"
        if signal.get('order_block_present', False):
            institutional_info += f"\n🧱 *Order Block:* {signal.get('order_block_type', 'unknown')} (قوة: {signal.get('order_block_strength', 0):.3f})"
        
        alert_text = (
            f"{emoji} *إشارة تداول متطورة*\n\n"
            f"*الأصل:* {signal['symbol']}\n"
            f"*الاتجاه:* {direction_text}\n"
            f"*السعر:* ${signal['entry_price']:.2f}\n"
            f"{institutional_info}\n"
            f"*المؤشرات:*\n"
            f"📊 RVOL: {signal['rvol']:.2f}x\n"
            f"⚡ الزخم: {signal['momentum']:.2f}%\n"
            f"📈 RSI: {signal['rsi']:.1f}\n"
            f"💡 الثقة: {signal['confidence']:.0%}\n\n"
            f"*الوقت:* {signal['entry_time']}"
        )
        
        try:
            self.bot.send_message(CHAT_ID, alert_text, parse_mode='Markdown')
            logger.info(f"تم إرسال إشارة {signal['symbol']}")
            self.signals_sent += 1
            
            # حفظ الإشارة
            self.db.save_advanced_signal(signal)
            
        except Exception as e:
            logger.error(f"فشل إرسال الإشارة: {e}")
    
    def monitor_market(self):
        """مراقبة السوق"""
        logger.info("بدء مراقبة السوق المتطورة...")
        
        while self.is_running:
            try:
                current_time = time.time()
                
                for symbol in ASSETS_TO_MONITOR:
                    if symbol in self.last_signal_time:
                        if current_time - self.last_signal_time[symbol] < self.params.signal_cooldown:
                            continue
                    
                    analysis = self.analyzer.analyze_symbol(symbol)
                    
                    if analysis.get('available', False):
                        signal = self.analyzer.generate_signal(analysis)
                        
                        if signal:
                            self.send_signal_alert(signal)
                            self.last_signal_time[symbol] = current_time
                
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"خطأ في المراقبة: {e}")
                time.sleep(30)
    
    def run(self):
        """تشغيل البوت"""
        # Monitor Asia's opening-range breaks via ES/NQ futures proxies.
        # This uses the existing Render Telegram secrets; no new account required.
        if os.getenv("ASIA_WATCH_ENABLED", "true").lower() == "true":
            try:
                from asia_watch import start_worker
                start_worker(TELEGRAM_TOKEN, CHAT_ID)
            except Exception as exc:
                logger.warning("Asia watcher cannot start: %s", type(exc).__name__)
        # NYSE watcher shares outbound Telegram credentials with Asia watcher.
        if os.getenv("US_WATCH_ENABLED", "true").lower() == "true":
            try:
                from us_watch import start_worker as start_us_worker
                start_us_worker(TELEGRAM_TOKEN, CHAT_ID)
            except Exception as exc:
                logger.warning("US watcher unavailable: %s", type(exc).__name__)
        # تشغيل Flask
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # The legacy scanner uses unverified Yahoo data and must not flood
        # price requests when market data is stale or unavailable.
        if os.getenv("ENABLE_LEGACY_MONITOR", "false").lower() == "true":
            monitor_thread = threading.Thread(target=self.monitor_market, daemon=True)
            monitor_thread.start()
            learning_thread = threading.Thread(
                target=self.learning_system.run_evaluation_loop,
                args=(self.analyzer,),
                daemon=True
            )
            learning_thread.start()
        else:
            logger.info("Legacy signals disabled until data validation is complete")

        # Polling is optional: simultaneous instances cause Telegram 409.
        # Outbound Telegram alerts still work when incoming polling is disabled.
        if os.getenv("ENABLE_TELEGRAM_POLLING", "false").lower() != "true":
            logger.info("Telegram getUpdates disabled: outbound notifications stay enabled")
            while self.is_running:
                time.sleep(60)
            return

        logger.info("بدء بوت التليجرام...")
        while self.is_running:
            try:
                self.bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
            except Exception as e:
                logger.error("Telegram polling error: %s", type(e).__name__)
                time.sleep(15)

# ==================== خادم Flask ====================
app = Flask(__name__)
START_TIME = time.time()

@app.route('/')
def home():
    return jsonify({
        'status': 'active',
        'system': 'Evolutionary Trading Bot with Institutional Footprints',
        'uptime': time.time() - START_TIME,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'uptime': time.time() - START_TIME
    })

def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ==================== نقطة البداية ====================
def main():
    try:
        bot = EvolutionaryTradingBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("إيقاف النظام...")
    except Exception as e:
        logger.error(f"خطأ قاتل: {e}")
        raise

if __name__ == "__main__":
    main()