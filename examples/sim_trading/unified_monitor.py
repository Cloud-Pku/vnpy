"""
统一监控平台 - 整合资金和Tick监控
- 账户资金概览
- 实时Tick价格监控
- 策略交易动作标记
- 持仓和盈亏统计
"""
import json
import re
import sqlite3
import threading
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 配置
DB_PATH = Path.home() / ".vntrader" / "database.db"
LOG_PATH = Path.home() / ".vntrader" / "log"

# 监控品种
MONITORED_SYMBOLS = [
    "rb2605.SHFE",
    "i2605.DCE",
    "MA605.CZCE",
    "SA605.CZCE",
    "p2605.DCE",
]

# 品种名称映射（用于日志解析）
SYMBOL_NAME_MAP = {
    "螺纹": "rb2605.SHFE",
    "铁矿": "i2605.DCE",
    "甲醇": "MA605.CZCE",
    "纯碱": "SA605.CZCE",
    "棕榈": "p2605.DCE",
}

# 合约乘数配置（吨/手）
CONTRACT_MULTIPLIERS = {
    'rb2605': 10,   # 螺纹钢 10吨/手
    'i2605': 100,   # 铁矿石 100吨/手
    'MA605': 10,    # 甲醇 10吨/手
    'SA605': 20,    # 纯碱 20吨/手
    'p2605': 10,    # 棕榈油 10吨/手
}

# 初始本金
INITIAL_CAPITAL = 1000000.0

# 数据缓存
data_cache = {
    'bars': {},
    'account': {
        'balance': INITIAL_CAPITAL,
        'available': INITIAL_CAPITAL,
        'frozen': 0.0,
        'pnl': 0.0,
        'positions': {}
    },
    'actions': [],
    'trades': {},  # 每个品种的交易记录
    'last_update': None
}
cache_lock = threading.Lock()


@dataclass
class TradeSignal:
    """交易信号"""
    time: str
    action: str  # BUY, SELL, COVER, SHORT
    price: float
    volume: int
    pos_after: int
    
    def to_dict(self):
        return {
            'time': self.time,
            'action': self.action,
            'price': self.price,
            'volume': self.volume,
            'pos_after': self.pos_after
        }


def is_trading_time(dt: datetime) -> bool:
    """检查是否在交易时段内
    
    商品期货交易时间：
    - 日盘：09:00-11:30, 13:30-15:00
    - 夜盘：21:00-23:00（大部分品种）
    - 部分品种夜盘到01:00或02:30（未单独处理，统一按23:00）
    """
    t = dt.time()
    # 日盘
    if dt_time(9, 0) <= t <= dt_time(11, 30):
        return True
    if dt_time(13, 30) <= t <= dt_time(15, 0):
        return True
    # 夜盘（21:00-23:00）
    if dt_time(21, 0) <= t <= dt_time(23, 0):
        return True
    # 部分品种夜盘延长到01:00或02:30（简化处理）
    # if dt_time(0, 0) <= t <= dt_time(2, 30):
    #     return True
    return False


def get_trades_from_db(date_str: str = None) -> Dict[str, List[TradeSignal]]:
    """从数据库读取交易记录（比日志解析更可靠）"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    trades_by_symbol: Dict[str, List[TradeSignal]] = {s: [] for s in MONITORED_SYMBOLS}
    
    # 建立symbol到完整格式的映射 (p2605 -> p2605.DCE)
    symbol_map = {}
    for full_symbol in MONITORED_SYMBOLS:
        parts = full_symbol.split('.')
        if len(parts) == 2:
            sym, exchange = parts
            symbol_map[sym] = full_symbol
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # 查询当日交易记录
        cursor.execute('''
            SELECT symbol, action, price, volume, pos_after, trade_datetime
            FROM trade_records 
            WHERE trade_date = ?
            ORDER BY trade_datetime
        ''', (date_str,))
        
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            symbol = row[0]  # 数据库中的symbol可能不含交易所后缀
            action = row[1]
            price = row[2]
            volume = row[3]
            pos_after = row[4]
            trade_datetime = row[5]
            
            # 提取时间 HH:MM
            time_str = trade_datetime[11:16] if trade_datetime else ""
            
            # 匹配到完整的symbol格式
            full_symbol = symbol_map.get(symbol, symbol)
            if full_symbol in trades_by_symbol:
                trades_by_symbol[full_symbol].append(TradeSignal(
                    time=time_str,
                    action=action,
                    price=price,
                    volume=volume,
                    pos_after=pos_after
                ))
        
    except Exception as e:
        print(f"读取交易记录错误: {e}")
    
    return trades_by_symbol


def parse_log_for_trades(date_str: str = None) -> Dict[str, List[TradeSignal]]:
    """从日志解析交易信号 - 备用方案（优先使用数据库）"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    log_file = LOG_PATH / f"vt_{date_str}.log"
    if not log_file.exists():
        return {}
    
    trades_by_symbol: Dict[str, List[TradeSignal]] = {s: [] for s in MONITORED_SYMBOLS}
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        for line in lines:
            # 提取时间 (支持毫秒: 2026-04-16 22:08:00.255)
            time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}):\d{2}', line)
            if not time_match:
                continue
            
            time_str = time_match.group(1)[11:16]  # 只取 HH:MM
            
            # 查找品种 - 通过策略名称匹配
            symbol = None
            for name, sym in SYMBOL_NAME_MAP.items():
                # 匹配策略名称格式: [RSI高频_螺纹] 或 RSI高频_螺纹
                pattern = f"RSI高频_{name}"
                if pattern in line:
                    symbol = sym
                    break
            
            if not symbol:
                continue
            
            # 只匹配真实成交记录: [成交] 买入开仓 / [成交] 卖出平仓
            trade_match = re.search(r'\[成交\].*?价格=(?P<price>[\d.]+)', line)
            if trade_match:
                price = float(trade_match.group('price'))
                pos_match = re.search(r'持仓=(?P<pos>-?\d+)', line)
                pos = int(pos_match.group('pos')) if pos_match else 0
                
                # 使用买入/卖出 + 开仓/平仓 组合判断
                is_buy = '买入' in line
                is_open = '开仓' in line
                
                if is_buy and is_open:
                    trade_action = 'BUY'
                elif is_buy and not is_open:
                    trade_action = 'COVER'
                elif not is_buy and is_open:
                    trade_action = 'SHORT'
                else:
                    trade_action = 'SELL'
                
                trades_by_symbol[symbol].append(TradeSignal(
                    time=time_str,
                    action=trade_action,
                    price=price,
                    volume=1,
                    pos_after=pos
                ))
    
    except Exception as e:
        print(f"解析交易日志错误: {e}")
    
    return trades_by_symbol


def calculate_pnl_from_trades(trades: List[TradeSignal], current_price: float,
                              contract_multiplier: int = 10) -> Tuple[float, float, int]:
    """根据交易记录计算盈亏和当前持仓
    
    Args:
        trades: 交易记录列表
        current_price: 当前价格
        contract_multiplier: 合约乘数（每吨价格），默认10吨/手
    
    Returns:
        (总盈亏, 已实现盈亏, 持仓)
    """
    pos = 0
    cost = 0.0  # 当前持仓的总成本
    realized_pnl = 0.0  # 已实现盈亏
    
    for trade in trades:
        if trade.action == 'BUY':
            if pos >= 0:
                # 买入开仓或加仓（多仓增加）
                cost += trade.price * trade.volume
                pos += trade.volume
            else:
                # 买入平仓（平空）- 空仓减少
                # 按先进先出原则计算盈亏
                avg_cost = cost / abs(pos) if pos < 0 else 0
                close_volume = min(trade.volume, abs(pos))
                # 已实现盈亏 = (开仓均价 - 买入价) × 平仓手数 × 合约乘数
                realized_pnl += (avg_cost - trade.price) * close_volume * contract_multiplier
                # 更新成本和持仓
                cost_per_unit = cost / abs(pos) if pos != 0 else 0
                cost -= cost_per_unit * close_volume
                pos += trade.volume
                # 如果还有剩余，转为多仓
                if pos > 0:
                    cost = trade.price * pos
                    
        elif trade.action == 'SHORT':
            if pos <= 0:
                # 卖出开仓或加仓（空仓增加）
                cost += trade.price * trade.volume
                pos -= trade.volume
            else:
                # 卖出平仓（平多）- 多仓减少
                avg_cost = cost / pos if pos > 0 else 0
                close_volume = min(trade.volume, pos)
                # 已实现盈亏 = (卖出价 - 成本价) × 平仓手数 × 合约乘数
                realized_pnl += (trade.price - avg_cost) * close_volume * contract_multiplier
                # 更新成本和持仓
                cost_per_unit = cost / pos if pos != 0 else 0
                cost -= cost_per_unit * close_volume
                pos -= trade.volume
                # 如果还有剩余，转为空仓
                if pos < 0:
                    cost = trade.price * abs(pos)
                    
        elif trade.action == 'SELL':
            # 卖出平仓（平多）
            if pos > 0:
                avg_cost = cost / pos
                close_volume = min(trade.volume, pos)
                # 已实现盈亏 = (卖出价 - 成本价) × 平仓手数 × 合约乘数
                realized_pnl += (trade.price - avg_cost) * close_volume * contract_multiplier
                # 更新成本
                cost_per_unit = cost / pos
                cost -= cost_per_unit * close_volume
                pos -= trade.volume
                # 如果平仓后持仓为0，成本也清0
                if pos == 0:
                    cost = 0.0
                    
        elif trade.action == 'COVER':
            # 买入平仓（平空）
            if pos < 0:
                avg_cost = cost / abs(pos)
                close_volume = min(trade.volume, abs(pos))
                # 已实现盈亏 = (开仓均价 - 买入价) × 平仓手数 × 合约乘数
                realized_pnl += (avg_cost - trade.price) * close_volume * contract_multiplier
                # 更新成本
                cost_per_unit = cost / abs(pos)
                cost -= cost_per_unit * close_volume
                pos += trade.volume
                # 如果平仓后持仓为0，成本也清0
                if pos == 0:
                    cost = 0.0
    
    # 计算浮动盈亏
    if pos > 0:
        # 多仓浮动盈亏 = (当前价 - 持仓均价) × 持仓 × 合约乘数
        avg_cost = cost / pos if pos > 0 else 0
        unrealized = (current_price - avg_cost) * pos * contract_multiplier
    elif pos < 0:
        # 空仓浮动盈亏 = (持仓均价 - 当前价) × |持仓| × 合约乘数
        avg_cost = cost / abs(pos) if pos < 0 else 0
        unrealized = (avg_cost - current_price) * abs(pos) * contract_multiplier
    else:
        unrealized = 0.0
    
    total_pnl = realized_pnl + unrealized
    return total_pnl, realized_pnl, pos


def load_latest_data():
    """从数据库加载最新数据并计算盈亏"""
    global data_cache
    
    if not DB_PATH.exists():
        return
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        total_pnl = 0.0
        total_frozen = 0.0
        
        # 从数据库加载交易记录（今天）
        trades = get_trades_from_db(today.replace('-', ''))
        
        # 如果今天没有交易记录，尝试加载昨天的（非交易时段回显历史数据）
        if not any(trades.values()):
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            trades = get_trades_from_db(yesterday)
        
        for symbol in MONITORED_SYMBOLS:
            parts = symbol.split('.')
            if len(parts) != 2:
                continue
            
            sym, exchange = parts
            
            # 查询今日K线数据
            cursor.execute("""
                SELECT datetime, open_price, high_price, low_price, close_price, volume
                FROM dbbardata
                WHERE symbol = ? AND exchange = ? 
                AND datetime >= ?
                AND interval = '1m'
                ORDER BY datetime DESC
                LIMIT 200
            """, (sym, exchange, today))
            
            rows = cursor.fetchall()
            
            # 如果今天没有数据，查询最近的K线数据
            if not rows:
                cursor.execute("""
                    SELECT datetime, open_price, high_price, low_price, close_price, volume
                    FROM dbbardata
                    WHERE symbol = ? AND exchange = ? 
                    AND interval = '1m'
                    ORDER BY datetime DESC
                    LIMIT 200
                """, (sym, exchange))
                rows = cursor.fetchall()
            
            # 过滤掉收盘无效K线（volume=0 且 OHLC全部相同）
            # 这是收盘时刻常见现象：交易不活跃，价格无变化，无成交
            # 同时过滤DCE日汇总K线（volume>10000 且 OHLC全部相同 且 时间是15:31）
            valid_rows = []
            for row in rows:
                datetime_str = row[0] if row[0] else ""
                is_1531 = "15:31:" in datetime_str
                ohlc_same = row[1] == row[2] == row[3] == row[4]
                volume = row[5] if row[5] else 0
                
                # 过滤条件1: volume=0 且 OHLC相同（收盘无效K线）
                if volume == 0 and ohlc_same:
                    continue
                
                # 过滤条件2: DCE日汇总K线（volume>10000 且 OHLC相同 且 15:31）
                if volume > 10000 and ohlc_same and is_1531:
                    print(f"[过滤] {sym} 日汇总K线: {datetime_str}, volume={volume}")
                    continue
                
                valid_rows.append(row)
            
            # 如果全部被过滤，保留原始数据
            if not valid_rows:
                valid_rows = rows
            
            # 获取最新价格
            current_price = valid_rows[0][4] if valid_rows else 0.0
            
            # 计算该品种的盈亏和持仓
            symbol_trades = trades.get(symbol, [])
            # 获取合约乘数
            sym_base = symbol.split('.')[0] if '.' in symbol else symbol
            multiplier = CONTRACT_MULTIPLIERS.get(sym_base, 10)
            symbol_pnl, symbol_realized_pnl, _ = calculate_pnl_from_trades(symbol_trades, current_price, multiplier)
            
            # 使用数据库中的最新持仓（而不是重新计算）
            # 重新计算可能因同一秒内多笔交易导致错误
            symbol_pos = 0
            if symbol_trades:
                symbol_pos = symbol_trades[-1].pos_after
            
            # 计算浮动盈亏 = 总盈亏 - 已实现盈亏
            symbol_unrealized_pnl = symbol_pnl - symbol_realized_pnl
            
            # 使用有效K线数据构建返回给前端的数据
            display_rows = valid_rows if valid_rows else rows
            
            with cache_lock:
                data_cache['bars'][symbol] = [
                    {
                        'time': row[0][11:16] if row[0] else '',
                        'datetime': row[0],
                        'open': row[1],
                        'high': row[2],
                        'low': row[3],
                        'close': row[4],
                        'volume': row[5]
                    }
                    for row in reversed(display_rows)
                ]
                
                data_cache['account']['positions'][symbol] = {
                    'price': current_price,
                    'pos': symbol_pos,
                    'pnl': symbol_unrealized_pnl,  # 浮动盈亏
                    'realized_pnl': symbol_realized_pnl  # 已实现盈亏（累计收益）
                }
                
                # 累加总盈亏
                total_pnl += symbol_pnl
                
                # 计算冻结资金（简化：每手保证金约为合约价值的10%）
                if symbol_pos != 0:
                    contract_value = current_price * 10  # 假设每手10吨
                    margin = contract_value * 0.10  # 10%保证金
                    total_frozen += margin * abs(symbol_pos)
        
        conn.close()
        
        # 更新账户信息
        with cache_lock:
            data_cache['account']['pnl'] = total_pnl
            data_cache['account']['balance'] = INITIAL_CAPITAL + total_pnl
            data_cache['account']['frozen'] = total_frozen
            data_cache['account']['available'] = data_cache['account']['balance'] - total_frozen
            data_cache['trades'] = {s: [t.to_dict() for t in trades.get(s, [])] for s in MONITORED_SYMBOLS}
            data_cache['last_update'] = datetime.now().strftime("%H:%M:%S")
            
    except Exception as e:
        print(f"加载数据错误: {e}")


def background_data_loader():
    """后台数据加载线程"""
    while True:
        load_latest_data()
        time.sleep(5)


# 启动后台线程
loader_thread = threading.Thread(target=background_data_loader, daemon=True)
loader_thread.start()


# 统一的HTML模板
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>量化交易监控中心</title>
    <!-- 移除自动刷新，改为手动刷新 -->
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e27;
            color: #e0e6ed;
            padding: 20px;
            line-height: 1.6;
        }
        
        /* 头部 */
        .header {
            text-align: center;
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid #1e3a5f;
        }
        .header h1 {
            color: #00d4ff;
            font-size: 28px;
            margin-bottom: 8px;
        }
        .header .subtitle {
            color: #8b92a8;
            font-size: 14px;
        }
        
        /* 账户资金卡片 */
        .account-section {
            background: linear-gradient(135deg, #1a1f3a 0%, #0f1525 100%);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid #2a3f5f;
        }
        .account-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .account-title {
            font-size: 18px;
            color: #ffd700;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .account-subtitle {
            font-size: 12px;
            color: #8b92a8;
        }
        .account-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
        }
        .account-item {
            background: rgba(0,0,0,0.2);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            border-left: 3px solid #00d4ff;
        }
        .account-item.profit { border-left-color: #00ff88; }
        .account-item.loss { border-left-color: #ff4757; }
        .account-label {
            font-size: 12px;
            color: #8b92a8;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .account-value {
            font-size: 26px;
            font-weight: bold;
            color: #fff;
        }
        .account-value.positive { color: #00ff88; }
        .account-value.negative { color: #ff4757; }
        
        /* 状态栏 */
        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #1a1f3a;
            padding: 15px 25px;
            border-radius: 10px;
            margin-bottom: 25px;
            border: 1px solid #2a3f5f;
        }
        .status-item {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-label {
            color: #8b92a8;
            font-size: 13px;
        }
        .status-value {
            color: #00d4ff;
            font-weight: bold;
            font-size: 16px;
        }
        .status-badge {
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .status-badge.trading {
            background: #00ff8833;
            color: #00ff88;
        }
        .status-badge.closed {
            background: #ff475733;
            color: #ff4757;
        }
        
        /* 品种网格 */
        .symbols-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
        }
        
        /* 品种卡片 */
        .symbol-card {
            background: #1a1f3a;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a3f5f;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .symbol-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,212,255,0.1);
        }
        .symbol-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #2a3f5f;
        }
        .symbol-name {
            font-size: 16px;
            font-weight: bold;
            color: #00d4ff;
        }
        .symbol-exchange {
            font-size: 11px;
            color: #8b92a8;
            background: rgba(0,212,255,0.1);
            padding: 3px 8px;
            border-radius: 4px;
        }
        
        /* 价格显示 */
        .price-section {
            display: flex;
            align-items: baseline;
            gap: 15px;
            margin-bottom: 15px;
        }
        .price-main {
            font-size: 36px;
            font-weight: bold;
        }
        .price-up { color: #00ff88; }
        .price-down { color: #ff4757; }
        .price-flat { color: #e0e6ed; }
        .price-change {
            font-size: 16px;
            padding: 4px 10px;
            border-radius: 6px;
            background: rgba(0,0,0,0.3);
        }
        
        /* OHLC统计 */
        .ohlc-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 15px;
        }
        .ohlc-item {
            text-align: center;
            padding: 10px;
            background: rgba(0,0,0,0.2);
            border-radius: 6px;
        }
        
        /* 持仓盈亏区域 */
        .position-section {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 15px;
            margin-bottom: 15px;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            border-left: 3px solid #00d4ff;
        }
        .pos-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .pos-label {
            color: #8b92a8;
            font-size: 13px;
        }
        .pos-value {
            font-weight: 600;
            font-size: 14px;
        }
        .pos-long {
            color: #00ff88;
        }
        .pos-short {
            color: #ff4757;
        }
        .pnl-value {
            font-weight: 700;
            font-size: 16px;
        }
        .pnl-profit {
            color: #00ff88;
        }
        .pnl-loss {
            color: #ff4757;
        }
        .pnl-flat {
            color: #8b92a8;
        }
        .ohlc-label {
            font-size: 11px;
            color: #8b92a8;
            margin-bottom: 4px;
        }
        .ohlc-value {
            font-size: 14px;
            font-weight: bold;
        }
        
        /* 走势图 */
        .chart-container {
            height: 100px;
            margin-top: 15px;
            position: relative;
            cursor: pointer;
        }
        .chart-container:hover {
            opacity: 0.8;
        }
        
        /* 模态框 */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            backdrop-filter: blur(5px);
        }
        .modal-content {
            background: #1a1f3a;
            margin: 5% auto;
            padding: 30px;
            border-radius: 15px;
            border: 1px solid #2a3f5f;
            width: 90%;
            max-width: 1000px;
            max-height: 80vh;
            overflow-y: auto;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #2a3f5f;
        }
        .modal-title {
            font-size: 20px;
            color: #00d4ff;
            font-weight: bold;
        }
        .modal-close {
            color: #8b92a8;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            transition: color 0.3s;
        }
        .modal-close:hover {
            color: #ff4757;
        }
        .modal-chart-container {
            position: relative;
            height: 400px;
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 20px;
        }
        .modal-legend {
            display: flex;
            gap: 20px;
            margin-top: 15px;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: #e0e6ed;
        }
        .legend-shape {
            width: 16px;
            height: 16px;
        }
        
        /* 交易信号标记 */
        .trade-signals {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #2a3f5f;
        }
        .trade-signals-title {
            font-size: 12px;
            color: #8b92a8;
            margin-bottom: 8px;
        }
        .signal-list {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        .signal-badge {
            font-size: 10px;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: bold;
        }
        .signal-buy {
            background: #00ff8833;
            color: #00ff88;
        }
        .signal-sell {
            background: #ff475733;
            color: #ff4757;
        }
        .signal-cover {
            background: #ffd70033;
            color: #ffd700;
        }
        .signal-short {
            background: #ff6b6b33;
            color: #ff6b6b;
        }
        
        /* 无数据 */
        .no-data {
            text-align: center;
            padding: 40px;
            color: #8b92a8;
        }
        
        /* 页脚 */
        .footer {
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #1e3a5f;
            color: #8b92a8;
            font-size: 12px;
        }
        
        /* 刷新按钮 */
        .refresh-btn {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #00d4ff;
            color: #0a0e27;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            z-index: 100;
        }
        .refresh-btn:hover {
            background: #00ff88;
        }
    </style>
</head>
<body>
    <button class="refresh-btn" onclick="location.reload()">🔄 刷新数据</button>
    
    <div class="header">
        <h1>📊 量化交易监控中心</h1>
        <div class="subtitle">SimNow 仿真交易 | 多品种策略交易池</div>
    </div>
    
    <!-- 账户资金 -->
    <div class="account-section">
        <div class="account-header">
            <div class="account-title">
                💰 账户资金
                <span class="account-subtitle">初始本金: {{ "{:,.0f}".format(initial_capital) }} CNY</span>
            </div>
        </div>
        <div class="account-grid">
            <div class="account-item">
                <div class="account-label">账户余额</div>
                <div class="account-value">{{ "{:,.2f}".format(account.balance) }}</div>
            </div>
            <div class="account-item">
                <div class="account-label">可用资金</div>
                <div class="account-value">{{ "{:,.2f}".format(account.available) }}</div>
            </div>
            <div class="account-item">
                <div class="account-label">冻结资金</div>
                <div class="account-value">{{ "{:,.2f}".format(account.frozen) }}</div>
            </div>
            <div class="account-item {% if account.pnl >= 0 %}profit{% else %}loss{% endif %}">
                <div class="account-label">浮动盈亏</div>
                <div class="account-value {% if account.pnl >= 0 %}positive{% else %}negative{% endif %}">
                    {{ "+" if account.pnl >= 0 else "" }}{{ "{:,.2f}".format(account.pnl) }}
                </div>
            </div>
            <div class="account-item {% if account.pnl >= 0 %}profit{% else %}loss{% endif %}">
                <div class="account-label">收益率</div>
                <div class="account-value {% if account.pnl >= 0 %}positive{% else %}negative{% endif %}">
                    {{ "+" if account.pnl >= 0 else "" }}{{ "{:.2f}".format(account.pnl / initial_capital * 100) }}%
                </div>
            </div>
        </div>
    </div>
    
    <!-- 状态栏 -->
    <div class="status-bar">
        <div class="status-item">
            <span class="status-label">监控品种:</span>
            <span class="status-value">{{ total_symbols }}</span>
        </div>
        <div class="status-item">
            <span class="status-label">今日K线:</span>
            <span class="status-value">{{ total_bars }}</span>
        </div>
        <div class="status-item">
            <span class="status-label">最后更新:</span>
            <span class="status-value">{{ last_update }}</span>
        </div>
        <div class="status-item">
            <span class="status-badge {{ 'trading' if is_trading else 'closed' }}">
                {{ '交易中' if is_trading else '休市中' }}
            </span>
        </div>
    </div>
    
    <!-- 品种列表 -->
    <div class="symbols-grid">
        {% for symbol, data in symbols.items() %}
        <div class="symbol-card">
            <div class="symbol-header">
                <span class="symbol-name">{{ symbol.split('.')[0] }}</span>
                <span class="symbol-exchange">{{ symbol.split('.')[1] }}</span>
            </div>
            
            {% if data.bars %}
            {% set latest = data.bars[-1] %}
            {% set prev = data.bars[-2] if data.bars|length > 1 else latest %}
            {% set change = latest.close - prev.close %}
            {% set change_pct = (change / prev.close * 100) if prev.close else 0 %}
            
            <div class="price-section">
                <div class="price-main {% if change > 0 %}price-up{% elif change < 0 %}price-down{% else %}price-flat{% endif %}">
                    {{ "%.1f"|format(latest.close) }}
                </div>
                <div class="price-change {% if change > 0 %}price-up{% elif change < 0 %}price-down{% else %}price-flat{% endif %}">
                    {{ "+%.2f"|format(change_pct) if change >= 0 else "%.2f"|format(change_pct) }}%
                </div>
            </div>
            
            <div class="ohlc-grid">
                <div class="ohlc-item">
                    <div class="ohlc-label">开盘</div>
                    <div class="ohlc-value">{{ "%.1f"|format(latest.open) }}</div>
                </div>
                <div class="ohlc-item">
                    <div class="ohlc-label">最高</div>
                    <div class="ohlc-value">{{ "%.1f"|format(latest.high) }}</div>
                </div>
                <div class="ohlc-item">
                    <div class="ohlc-label">最低</div>
                    <div class="ohlc-value">{{ "%.1f"|format(latest.low) }}</div>
                </div>
                <div class="ohlc-item">
                    <div class="ohlc-label">成交量</div>
                    <div class="ohlc-value">{{ "%.0f"|format(latest.volume) }}</div>
                </div>
            </div>
            
            {% set pos_info = positions.get(symbol, {}) %}
            {% if pos_info.pos and pos_info.pos != 0 %}
            <div class="position-section">
                <div class="pos-item">
                    <span class="pos-label">持仓:</span>
                    <span class="pos-value {% if pos_info.pos > 0 %}pos-long{% else %}pos-short{% endif %}">
                        {{ pos_info.pos }}手 {{ "多" if pos_info.pos > 0 else "空" }}
                    </span>
                </div>
                <div class="pos-item">
                    <span class="pos-label">浮动盈亏:</span>
                    <span class="pnl-value {% if pos_info.pnl > 0 %}pnl-profit{% elif pos_info.pnl < 0 %}pnl-loss{% else %}pnl-flat{% endif %}">
                        {{ "+%.0f"|format(pos_info.pnl) if pos_info.pnl >= 0 else "%.0f"|format(pos_info.pnl) }}元
                    </span>
                </div>
            </div>
            {% endif %}
            
            {# 累计收益（无论是否有持仓都显示）#}
            {% if pos_info.realized_pnl is defined and pos_info.realized_pnl != 0 %}
            <div class="position-section" style="border-left-color: #ffd700;">
                <div class="pos-item">
                    <span class="pos-label">累计收益:</span>
                    <span class="pnl-value {% if pos_info.realized_pnl > 0 %}pnl-profit{% elif pos_info.realized_pnl < 0 %}pnl-loss{% else %}pnl-flat{% endif %}">
                        {{ "+%.0f"|format(pos_info.realized_pnl) if pos_info.realized_pnl >= 0 else "%.0f"|format(pos_info.realized_pnl) }}元
                    </span>
                </div>
            </div>
            {% endif %}
            
            <div class="chart-container" onclick="openModal('{{ symbol }}')">
                <canvas id="chart-{{ symbol.replace('.', '-') }}" width="280" height="100"></canvas>
                <div style="text-align: center; font-size: 11px; color: #8b92a8; margin-top: 5px;">点击查看详细图表</div>
            </div>
            
            {% if data.trades %}
            <div class="trade-signals">
                <div class="trade-signals-title">📊 交易信号 ({{ data.trades|length }})</div>
                <div class="signal-list">
                    {% for trade in data.trades[-5:] %}  {# 只显示最近5个 #}
                    <span class="signal-badge signal-{{ trade.action|lower }}">
                        {{ trade.time }} {{ trade.action }} @{{ "%.1f"|format(trade.price) if trade.price else '-' }} 
                        持仓:{{ trade.pos_after }}
                    </span>
                    {% endfor %}
                </div>
            </div>
            {% endif %}
            
            <script>
                (function() {
                    const canvas = document.getElementById('chart-{{ symbol.replace('.', '-') }}');
                    const ctx = canvas.getContext('2d');
                    
                    const data = {{ data.bars | tojson }};
                    const trades = {{ data.trades | tojson }} || [];
                    
                    console.log('[{{ symbol }}] K线数据点数:', data.length);
                    console.log('[{{ symbol }}] 交易信号数:', trades.length);
                    if (trades.length > 0) {
                        console.log('[{{ symbol }}] 交易信号:', trades.map(t => t.time + ' ' + t.action));
                    }
                    if (data.length > 0) {
                        console.log('[{{ symbol }}] K线时间范围:', data[0].time, '-', data[data.length-1].time);
                    }
                    
                    if (data.length < 2) return;
                    
                    const prices = data.map(d => d.close);
                    const min = Math.min(...prices);
                    const max = Math.max(...prices);
                    const range = max - min || 1;
                    
                    const width = canvas.width;
                    const height = canvas.height;
                    const padding = 5;
                    
                    // 清除
                    ctx.clearRect(0, 0, width, height);
                    
                    // 绘制区域背景
                    const isUp = {{ 'true' if change >= 0 else 'false' }};
                    ctx.fillStyle = isUp ? 'rgba(0, 255, 136, 0.05)' : 'rgba(255, 71, 87, 0.05)';
                    ctx.fillRect(0, 0, width, height);
                    
                    // 绘制线条
                    ctx.strokeStyle = isUp ? '#00ff88' : '#ff4757';
                    ctx.lineWidth = 2;
                    ctx.lineCap = 'round';
                    ctx.lineJoin = 'round';
                    
                    ctx.beginPath();
                    data.forEach((d, i) => {
                        const x = padding + (i / (data.length - 1)) * (width - padding * 2);
                        const y = height - padding - ((d.close - min) / range) * (height - padding * 2);
                        if (i === 0) ctx.moveTo(x, y);
                        else ctx.lineTo(x, y);
                    });
                    ctx.stroke();
                    
                    // 绘制交易信号标记
                    let matchedTrades = 0;
                    trades.forEach(trade => {
                        // 找到对应时间的数据点 (trade.time是HH:MM, data.time也是HH:MM)
                        const tradeTime = trade.time;
                        // 尝试精确匹配，如果没有则找最近的时间点
                        let dataIndex = data.findIndex(d => d.time === tradeTime);
                        
                        // 如果没找到，尝试匹配小时和分钟的前缀
                        if (dataIndex < 0) {
                            for (let i = 0; i < data.length; i++) {
                                if (data[i].time && data[i].time.substring(0, 5) === tradeTime.substring(0, 5)) {
                                    dataIndex = i;
                                    break;
                                }
                            }
                        }
                        
                        if (dataIndex >= 0) {
                            matchedTrades++;
                            console.log('[{{ symbol }}] 绘制标记:', trade.action, '@', trade.time, '索引:', dataIndex);
                            const x = padding + (dataIndex / (data.length - 1)) * (width - padding * 2);
                            const price = data[dataIndex].close;
                            const y = height - padding - ((price - min) / range) * (height - padding * 2);
                            
                            // 根据动作选择颜色和形状
                            let color, shape;
                            switch(trade.action) {
                                case 'BUY':
                                    color = '#00ff88';
                                    shape = 'triangle';
                                    break;
                                case 'SELL':
                                    color = '#ff4757';
                                    shape = 'triangle-down';
                                    break;
                                case 'COVER':
                                    color = '#ffd700';
                                    shape = 'circle';
                                    break;
                                case 'SHORT':
                                    color = '#ff6b6b';
                                    shape = 'square';
                                    break;
                                default:
                                    color = '#fff';
                                    shape = 'circle';
                            }
                            
                            ctx.fillStyle = color;
                            ctx.strokeStyle = color;
                            ctx.lineWidth = 2;
                            
                            if (shape === 'triangle') {
                                // 向上三角形（买入）
                                ctx.beginPath();
                                ctx.moveTo(x, y - 8);
                                ctx.lineTo(x - 6, y + 4);
                                ctx.lineTo(x + 6, y + 4);
                                ctx.closePath();
                                ctx.fill();
                            } else if (shape === 'triangle-down') {
                                // 向下三角形（卖出）
                                ctx.beginPath();
                                ctx.moveTo(x, y + 8);
                                ctx.lineTo(x - 6, y - 4);
                                ctx.lineTo(x + 6, y - 4);
                                ctx.closePath();
                                ctx.fill();
                            } else if (shape === 'circle') {
                                // 圆形（平仓）
                                ctx.beginPath();
                                ctx.arc(x, y, 5, 0, Math.PI * 2);
                                ctx.fill();
                            } else {
                                // 方形（开仓）
                                ctx.fillRect(x - 5, y - 5, 10, 10);
                            }
                        }
                    });
                    
                    // 绘制终点圆点
                    const lastX = width - padding;
                    const lastY = height - padding - ((prices[prices.length - 1] - min) / range) * (height - padding * 2);
                    ctx.fillStyle = isUp ? '#00ff88' : '#ff4757';
                    ctx.beginPath();
                    ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
                    ctx.fill();
                    
                    console.log('[{{ symbol }}] 成功匹配并绘制:', matchedTrades, '/', trades.length, '个交易标记');
                })();
            </script>
            {% else %}
            <div class="no-data">暂无数据</div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    
    <!-- 模态框 -->
    <div id="detailModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modalTitle">详细图表</div>
                <span class="modal-close" onclick="closeModal()">&times;</span>
            </div>
            <div class="modal-chart-container">
                <canvas id="modalChart" width="900" height="350"></canvas>
            </div>
            <div class="modal-legend">
                <div class="legend-item">
                    <svg class="legend-shape" viewBox="0 0 20 20">
                        <polygon points="10,2 2,18 18,18" fill="#00ff88"/>
                    </svg>
                    <span>买入开仓 (BUY)</span>
                </div>
                <div class="legend-item">
                    <svg class="legend-shape" viewBox="0 0 20 20">
                        <polygon points="10,18 2,2 18,2" fill="#ff4757"/>
                    </svg>
                    <span>卖出平仓 (SELL)</span>
                </div>
                <div class="legend-item">
                    <svg class="legend-shape" viewBox="0 0 20 20">
                        <rect x="5" y="5" width="10" height="10" fill="#ff6b6b"/>
                    </svg>
                    <span>卖出开仓 (SHORT)</span>
                </div>
                <div class="legend-item">
                    <svg class="legend-shape" viewBox="0 0 20 20">
                        <circle cx="10" cy="10" r="6" fill="#ffd700"/>
                    </svg>
                    <span>买入平仓 (COVER)</span>
                </div>
            </div>
            <div id="tradeList" style="margin-top: 20px;"></div>
        </div>
    </div>

    <script>
        // 存储所有品种数据
        const allSymbolsData = {{ symbols | tojson }};
        
        console.log('=== 监控页面已加载 ===');
        console.log('品种数据:', Object.keys(allSymbolsData));
        
        function openModal(symbol) {
            console.log('打开模态框:', symbol);
            const modal = document.getElementById('detailModal');
            const title = document.getElementById('modalTitle');
            const data = allSymbolsData[symbol];
            
            title.textContent = symbol + ' - 详细走势图';
            modal.style.display = 'block';
            
            // 绘制详细图表
            drawModalChart(symbol, data);
            
            // 显示交易列表
            showTradeList(data.trades || []);
        }
        
        function closeModal() {
            document.getElementById('detailModal').style.display = 'none';
        }
        
        // 点击模态框外部关闭
        window.onclick = function(event) {
            const modal = document.getElementById('detailModal');
            if (event.target === modal) {
                closeModal();
            }
        }
        
        function drawModalChart(symbol, data) {
            console.log('绘制模态框图表:', symbol);
            console.log('数据:', data);
            
            const canvas = document.getElementById('modalChart');
            if (!canvas) {
                console.error('找不到canvas元素');
                return;
            }
            
            const ctx = canvas.getContext('2d');
            const bars = data.bars || [];
            const trades = data.trades || [];
            
            console.log('K线数:', bars.length, '交易信号数:', trades.length);
            
            if (bars.length < 2) {
                console.log('K线数据不足，无法绘制');
                return;
            }
            
            const prices = bars.map(d => d.close);
            const min = Math.min(...prices);
            const max = Math.max(...prices);
            const range = max - min || 1;
            
            // 图表区域设置
            const chartPadding = { top: 30, right: 80, bottom: 50, left: 70 };
            const chartWidth = canvas.width - chartPadding.left - chartPadding.right;
            const chartHeight = canvas.height - chartPadding.top - chartPadding.bottom;
            
            // 清除画布
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // 绘制背景网格
            ctx.strokeStyle = 'rgba(255,255,255,0.05)';
            ctx.lineWidth = 1;
            
            // 水平网格线 (5条)
            for (let i = 0; i <= 5; i++) {
                const y = chartPadding.top + (i / 5) * chartHeight;
                ctx.beginPath();
                ctx.moveTo(chartPadding.left, y);
                ctx.lineTo(chartPadding.left + chartWidth, y);
                ctx.stroke();
                
                // Y轴标签
                const price = max - (i / 5) * range;
                ctx.fillStyle = '#8b92a8';
                ctx.font = '12px Arial';
                ctx.textAlign = 'right';
                ctx.fillText(price.toFixed(1), chartPadding.left - 10, y + 4);
            }
            
            // 垂直网格线 (时间轴)
            const timeStep = Math.ceil(bars.length / 8);
            for (let i = 0; i < bars.length; i += timeStep) {
                const x = chartPadding.left + (i / (bars.length - 1)) * chartWidth;
                ctx.beginPath();
                ctx.moveTo(x, chartPadding.top);
                ctx.lineTo(x, chartPadding.top + chartHeight);
                ctx.stroke();
                
                // X轴标签
                ctx.fillStyle = '#8b92a8';
                ctx.font = '11px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(bars[i].time, x, chartPadding.top + chartHeight + 20);
            }
            
            // 绘制价格线
            const isUp = bars[bars.length - 1].close >= bars[0].close;
            ctx.strokeStyle = isUp ? '#00ff88' : '#ff4757';
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            
            ctx.beginPath();
            bars.forEach((d, i) => {
                const x = chartPadding.left + (i / (bars.length - 1)) * chartWidth;
                const y = chartPadding.top + chartHeight - ((d.close - min) / range) * chartHeight;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();
            
            // 绘制填充区域
            ctx.fillStyle = isUp ? 'rgba(0, 255, 136, 0.1)' : 'rgba(255, 71, 87, 0.1)';
            ctx.lineTo(chartPadding.left + chartWidth, chartPadding.top + chartHeight);
            ctx.lineTo(chartPadding.left, chartPadding.top + chartHeight);
            ctx.closePath();
            ctx.fill();
            
            // 绘制坐标轴
            ctx.strokeStyle = '#2a3f5f';
            ctx.lineWidth = 2;
            ctx.beginPath();
            // Y轴
            ctx.moveTo(chartPadding.left, chartPadding.top);
            ctx.lineTo(chartPadding.left, chartPadding.top + chartHeight);
            // X轴
            ctx.moveTo(chartPadding.left, chartPadding.top + chartHeight);
            ctx.lineTo(chartPadding.left + chartWidth, chartPadding.top + chartHeight);
            ctx.stroke();
            
            // 绘制轴标签
            ctx.fillStyle = '#00d4ff';
            ctx.font = 'bold 13px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('时间', chartPadding.left + chartWidth / 2, canvas.height - 10);
            
            ctx.save();
            ctx.translate(20, chartPadding.top + chartHeight / 2);
            ctx.rotate(-Math.PI / 2);
            ctx.fillText('价格', 0, 0);
            ctx.restore();
            
            // 绘制交易信号标记
            let matchedCount = 0;
            console.log('开始匹配交易信号，trades:', trades.length, 'bars:', bars.length);
            console.log('bars时间范围:', bars[0].time, '-', bars[bars.length-1].time);
            console.log('前3个交易信号时间:', trades.slice(0,3).map(t => t.time));
            
            trades.forEach((trade, idx) => {
                // 尝试精确匹配
                let dataIndex = bars.findIndex(d => d.time === trade.time);
                
                // 如果没找到，尝试找到最接近的时间点（前后2分钟内）
                if (dataIndex < 0) {
                    const tradeMinutes = parseInt(trade.time.split(':')[0]) * 60 + parseInt(trade.time.split(':')[1]);
                    let minDiff = Infinity;
                    
                    for (let i = 0; i < bars.length; i++) {
                        const barTime = bars[i].time;
                        if (!barTime) continue;
                        const barMinutes = parseInt(barTime.split(':')[0]) * 60 + parseInt(barTime.split(':')[1]);
                        const diff = Math.abs(barMinutes - tradeMinutes);
                        
                        if (diff < minDiff && diff <= 2) { // 2分钟内
                            minDiff = diff;
                            dataIndex = i;
                        }
                    }
                }
                
                if (dataIndex >= 0) {
                    matchedCount++;
                    if (idx < 3) {
                        console.log(`匹配成功 [${idx}]: ${trade.action} @ ${trade.time} -> bars[${dataIndex}].time=${bars[dataIndex].time}`);
                    }
                    const x = chartPadding.left + (dataIndex / (bars.length - 1)) * chartWidth;
                    const price = bars[dataIndex].close;
                    const y = chartPadding.top + chartHeight - ((price - min) / range) * chartHeight;
                    
                    let color, label;
                    switch(trade.action) {
                        case 'BUY':
                            color = '#00ff88';
                            label = '买';
                            break;
                        case 'SELL':
                            color = '#ff4757';
                            label = '卖';
                            break;
                        case 'COVER':
                            color = '#ffd700';
                            label = '平';
                            break;
                        case 'SHORT':
                            color = '#ff6b6b';
                            label = '空';
                            break;
                        default:
                            color = '#fff';
                            label = '?';
                    }
                    
                    // 绘制标记
                    ctx.fillStyle = color;
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 2;
                    
                    if (trade.action === 'BUY') {
                        // 向上三角形
                        ctx.beginPath();
                        ctx.moveTo(x, y - 15);
                        ctx.lineTo(x - 8, y + 5);
                        ctx.lineTo(x + 8, y + 5);
                        ctx.closePath();
                        ctx.fill();
                    } else if (trade.action === 'SELL') {
                        // 向下三角形
                        ctx.beginPath();
                        ctx.moveTo(x, y + 15);
                        ctx.lineTo(x - 8, y - 5);
                        ctx.lineTo(x + 8, y - 5);
                        ctx.closePath();
                        ctx.fill();
                    } else if (trade.action === 'COVER') {
                        // 圆形
                        ctx.beginPath();
                        ctx.arc(x, y, 7, 0, Math.PI * 2);
                        ctx.fill();
                    } else {
                        // 方形
                        ctx.fillRect(x - 7, y - 7, 14, 14);
                    }
                    
                    // 绘制标签
                    ctx.fillStyle = color;
                    ctx.font = 'bold 11px Arial';
                    ctx.textAlign = 'center';
                    ctx.fillText(label + '@' + trade.price.toFixed(1), x, y - 20);
                } else {
                    if (idx < 3) {
                        console.log(`未匹配 [${idx}]: ${trade.action} @ ${trade.time}`);
                    }
                }
            });
            
            console.log(`交易信号匹配完成: ${matchedCount}/${trades.length} 个成功匹配`);
            
            // 绘制最新价格标签
            const lastPrice = prices[prices.length - 1];
            const lastY = chartPadding.top + chartHeight - ((lastPrice - min) / range) * chartHeight;
            ctx.fillStyle = isUp ? '#00ff88' : '#ff4757';
            ctx.font = 'bold 14px Arial';
            ctx.textAlign = 'left';
            ctx.fillText(lastPrice.toFixed(1), chartPadding.left + chartWidth + 10, lastY + 4);
        }
        
        function showTradeList(trades) {
            const container = document.getElementById('tradeList');
            if (trades.length === 0) {
                container.innerHTML = '<div style="color: #8b92a8; text-align: center; padding: 20px;">暂无交易记录</div>';
                return;
            }
            
            let html = '<h3 style="color: #00d4ff; margin-bottom: 15px;">📋 交易记录</h3>';
            html += '<table style="width: 100%; border-collapse: collapse; font-size: 13px;">';
            html += '<tr style="background: rgba(0,212,255,0.1);">';
            html += '<th style="padding: 10px; text-align: left; color: #8b92a8;">时间</th>';
            html += '<th style="padding: 10px; text-align: left; color: #8b92a8;">动作</th>';
            html += '<th style="padding: 10px; text-align: right; color: #8b92a8;">价格</th>';
            html += '<th style="padding: 10px; text-align: right; color: #8b92a8;">数量</th>';
            html += '<th style="padding: 10px; text-align: right; color: #8b92a8;">持仓</th>';
            html += '</tr>';
            
            trades.slice().reverse().forEach((trade, i) => {
                const actionColors = {
                    'BUY': '#00ff88',
                    'SELL': '#ff4757',
                    'SHORT': '#ff6b6b',
                    'COVER': '#ffd700'
                };
                const actionNames = {
                    'BUY': '买入开仓',
                    'SELL': '卖出平仓',
                    'SHORT': '卖出开仓',
                    'COVER': '买入平仓'
                };
                const bgColor = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)';
                html += `<tr style="background: ${bgColor};">`;
                html += `<td style="padding: 10px; color: #e0e6ed;">${trade.time}</td>`;
                html += `<td style="padding: 10px; color: ${actionColors[trade.action] || '#fff'}; font-weight: bold;">${actionNames[trade.action] || trade.action}</td>`;
                html += `<td style="padding: 10px; text-align: right; color: #e0e6ed;">${trade.price.toFixed(1)}</td>`;
                html += `<td style="padding: 10px; text-align: right; color: #e0e6ed;">${trade.volume}</td>`;
                html += `<td style="padding: 10px; text-align: right; color: ${trade.pos_after > 0 ? '#00ff88' : trade.pos_after < 0 ? '#ff4757' : '#8b92a8'};">${trade.pos_after}</td>`;
                html += '</tr>';
            });
            
            html += '</table>';
            container.innerHTML = html;
        }
    </script>
    
    <div class="footer">
        点击右上角按钮手动刷新 | 数据来源: SimNow CTP 仿真交易
    </div>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """统一监控面板"""
    with cache_lock:
        symbols_data = {}
        total_bars = 0
        
        for symbol in MONITORED_SYMBOLS:
            bars = data_cache['bars'].get(symbol, [])
            trades = data_cache['trades'].get(symbol, [])
            symbols_data[symbol] = {'bars': bars, 'trades': trades}
            total_bars += len(bars)
        
        account = data_cache['account']
        last_update = data_cache['last_update'] or "从未"
    
    now = datetime.now()
    is_trading = is_trading_time(now)
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        account=account,
        initial_capital=INITIAL_CAPITAL,
        symbols=symbols_data,
        positions=account['positions'],  # 各品种持仓和盈亏
        total_symbols=len(MONITORED_SYMBOLS),
        total_bars=total_bars,
        is_trading=is_trading,
        last_update=last_update
    )


@app.route('/api/data')
def api_data():
    """获取所有数据API"""
    with cache_lock:
        # 构建包含bars和trades的完整数据
        symbols_data = {}
        for symbol in MONITORED_SYMBOLS:
            symbols_data[symbol] = {
                'bars': data_cache['bars'].get(symbol, []),
                'trades': data_cache['trades'].get(symbol, [])
            }
        
        return jsonify({
            'account': data_cache['account'],
            'symbols': symbols_data,
            'last_update': data_cache['last_update'],
            'is_trading': is_trading_time(datetime.now()),
            'timestamp': datetime.now().isoformat()
        })


@app.route('/api/account')
def api_account():
    """获取账户信息"""
    with cache_lock:
        return jsonify({
            'initial_capital': INITIAL_CAPITAL,
            'account': data_cache['account'],
            'last_update': data_cache['last_update']
        })


def main():
    """启动统一监控服务"""
    print("=" * 60)
    print("🚀 统一监控平台")
    print("=" * 60)
    print("功能整合:")
    print("  ✅ 账户资金监控")
    print("  ✅ 实时Tick价格")
    print("  ✅ 策略持仓盈亏")
    print("  ✅ 交易时段状态")
    print("  ✅ 买卖点标记 (NEW)")
    print("=" * 60)
    print("访问地址: http://localhost:5002")
    print("=" * 60)
    
    load_latest_data()
    
    app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)


if __name__ == '__main__':
    main()
