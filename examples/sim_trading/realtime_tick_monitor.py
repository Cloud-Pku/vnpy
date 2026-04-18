"""
实时Tick监控Web服务 - 轻量级版本
- 实时显示Tick价格变化
- 扣除非交易时段
- 标记策略交易动作
- 使用WebSocket或轮询更新
"""
import json
import re
import sqlite3
import threading
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

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

# 数据缓存
data_cache = {
    'ticks': {},
    'bars': {},
    'actions': [],
    'last_update': None
}
cache_lock = threading.Lock()


def is_trading_time(dt: datetime) -> bool:
    """检查是否在交易时段内"""
    t = dt.time()
    if dt_time(9, 0) <= t <= dt_time(11, 30):
        return True
    if dt_time(13, 30) <= t <= dt_time(15, 0):
        return True
    if dt_time(21, 0) <= t <= dt_time(23, 59):
        return True
    if dt_time(0, 0) <= t <= dt_time(2, 30):
        return True
    return False


def parse_log_datetime(time_str: str) -> Optional[datetime]:
    """解析日志时间"""
    time_str = time_str.strip()
    if time_str.endswith('+08:00'):
        time_str = time_str[:-6]
    
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return None


def load_latest_data():
    """从数据库加载最新数据"""
    global data_cache
    
    if not DB_PATH.exists():
        return
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        for symbol in MONITORED_SYMBOLS:
            parts = symbol.split('.')
            if len(parts) != 2:
                continue
            
            sym, exchange = parts
            
            # 查询今日K线数据（限制100条，避免过多）
            cursor.execute("""
                SELECT datetime, open_price, high_price, low_price, close_price, volume
                FROM dbbardata
                WHERE symbol = ? AND exchange = ? 
                AND datetime >= ?
                AND interval = '1m'
                ORDER BY datetime DESC
                LIMIT 100
            """, (sym, exchange, today))
            
            rows = cursor.fetchall()
            
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
                    for row in reversed(rows)
                ]
        
        conn.close()
        
        with cache_lock:
            data_cache['last_update'] = datetime.now().strftime("%H:%M:%S")
            
    except Exception as e:
        print(f"加载数据错误: {e}")


def background_data_loader():
    """后台数据加载线程"""
    while True:
        load_latest_data()
        time.sleep(5)  # 每5秒刷新一次


# 启动后台线程
loader_thread = threading.Thread(target=background_data_loader, daemon=True)
loader_thread.start()


# HTML模板 - 轻量级实时版本
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>实时Tick监控</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 20px;
        }
        .header h1 {
            color: #58a6ff;
            font-size: 24px;
            margin-bottom: 5px;
        }
        .update-info {
            color: #8b949e;
            font-size: 12px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            max-width: 1600px;
            margin: 0 auto;
        }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 15px;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 10px;
            border-bottom: 1px solid #30363d;
        }
        .symbol-name {
            font-size: 16px;
            font-weight: bold;
            color: #58a6ff;
        }
        .status {
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 4px;
            background: #238636;
        }
        .status.inactive {
            background: #8b949e;
        }
        .price-main {
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }
        .price-up { color: #3fb950; }
        .price-down { color: #f85149; }
        .price-flat { color: #c9d1d9; }
        .stats-row {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            font-size: 12px;
        }
        .stat-item {
            text-align: center;
        }
        .stat-label {
            color: #8b949e;
            margin-bottom: 3px;
        }
        .stat-value {
            font-weight: bold;
        }
        .chart-container {
            margin-top: 15px;
            height: 100px;
            position: relative;
        }
        .sparkline {
            width: 100%;
            height: 100%;
        }
        .no-data {
            text-align: center;
            color: #8b949e;
            padding: 40px;
        }
        .actions-list {
            margin-top: 10px;
            font-size: 11px;
            max-height: 60px;
            overflow-y: auto;
        }
        .action-item {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            border-bottom: 1px solid #21262d;
        }
        .action-buy { color: #3fb950; }
        .action-sell { color: #f85149; }
        .summary-bar {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-around;
            max-width: 1600px;
            margin-left: auto;
            margin-right: auto;
        }
        .summary-item {
            text-align: center;
        }
        .summary-value {
            font-size: 24px;
            font-weight: bold;
            color: #58a6ff;
        }
        .summary-label {
            font-size: 12px;
            color: #8b949e;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📈 实时Tick监控面板</h1>
        <div class="update-info">最后更新: {{ last_update }} | 自动刷新: 10秒</div>
    </div>
    
    <div class="summary-bar">
        <div class="summary-item">
            <div class="summary-value">{{ total_symbols }}</div>
            <div class="summary-label">监控品种</div>
        </div>
        <div class="summary-item">
            <div class="summary-value">{{ total_bars }}</div>
            <div class="summary-label">今日K线</div>
        </div>
        <div class="summary-item">
            <div class="summary-value">{{ trading_status }}</div>
            <div class="summary-label">交易状态</div>
        </div>
    </div>
    
    <div class="grid">
        {% for symbol, data in symbols.items() %}
        <div class="card">
            <div class="card-header">
                <span class="symbol-name">{{ symbol }}</span>
                <span class="status {% if not data.bars %}inactive{% endif %}">
                    {% if data.bars %}交易中{% else %}等待数据{% endif %}
                </span>
            </div>
            
            {% if data.bars %}
            {% set latest = data.bars[-1] %}
            {% set prev = data.bars[-2] if data.bars|length > 1 else latest %}
            {% set change = latest.close - prev.close %}
            {% set change_pct = (change / prev.close * 100) if prev.close else 0 %}
            
            <div class="price-main {% if change > 0 %}price-up{% elif change < 0 %}price-down{% else %}price-flat{% endif %}">
                {{ "%.1f"|format(latest.close) }}
                <span style="font-size: 14px; margin-left: 10px;">
                    {{ "+%.2f"|format(change_pct) if change >= 0 else "%.2f"|format(change_pct) }}%
                </span>
            </div>
            
            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">开盘</div>
                    <div class="stat-value">{{ "%.1f"|format(latest.open) }}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">最高</div>
                    <div class="stat-value">{{ "%.1f"|format(latest.high) }}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">最低</div>
                    <div class="stat-value">{{ "%.1f"|format(latest.low) }}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">成交量</div>
                    <div class="stat-value">{{ "%.0f"|format(latest.volume) }}</div>
                </div>
            </div>
            
            <div class="chart-container">
                <canvas id="chart-{{ symbol.replace('.', '-') }}" class="sparkline"></canvas>
            </div>
            
            <script>
                (function() {
                    const canvas = document.getElementById('chart-{{ symbol.replace('.', '-') }}');
                    const ctx = canvas.getContext('2d');
                    canvas.width = canvas.offsetWidth;
                    canvas.height = canvas.offsetHeight;
                    
                    const data = {{ data.bars | tojson }};
                    if (data.length < 2) return;
                    
                    const prices = data.map(d => d.close);
                    const min = Math.min(...prices);
                    const max = Math.max(...prices);
                    const range = max - min || 1;
                    
                    ctx.strokeStyle = '{{ "#3fb950" if change >= 0 else "#f85149" }}';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    
                    data.forEach((d, i) => {
                        const x = (i / (data.length - 1)) * canvas.width;
                        const y = canvas.height - ((d.close - min) / range) * canvas.height * 0.8 - canvas.height * 0.1;
                        if (i === 0) ctx.moveTo(x, y);
                        else ctx.lineTo(x, y);
                    });
                    
                    ctx.stroke();
                })();
            </script>
            {% else %}
            <div class="no-data">暂无数据</div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """监控面板"""
    with cache_lock:
        symbols_data = {}
        total_bars = 0
        
        for symbol in MONITORED_SYMBOLS:
            bars = data_cache['bars'].get(symbol, [])
            symbols_data[symbol] = {'bars': bars}
            total_bars += len(bars)
        
        last_update = data_cache['last_update'] or "从未"
    
    # 检查交易状态
    now = datetime.now()
    is_trading = is_trading_time(now)
    trading_status = "交易中" if is_trading else "休市中"
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        symbols=symbols_data,
        total_symbols=len(MONITORED_SYMBOLS),
        total_bars=total_bars,
        trading_status=trading_status,
        last_update=last_update
    )


@app.route('/api/data')
def api_data():
    """获取实时数据API"""
    with cache_lock:
        return jsonify({
            'symbols': data_cache['bars'],
            'last_update': data_cache['last_update'],
            'timestamp': datetime.now().isoformat()
        })


@app.route('/api/symbols/<symbol>/history')
def api_symbol_history(symbol: str):
    """获取指定品种历史数据"""
    with cache_lock:
        bars = data_cache['bars'].get(symbol, [])
        return jsonify({
            'symbol': symbol,
            'count': len(bars),
            'data': bars
        })


def main():
    """启动服务"""
    print("=" * 60)
    print("实时Tick监控服务")
    print("=" * 60)
    print("特点:")
    print("- 轻量级Canvas绘制，不卡顿")
    print("- 每5秒自动刷新数据")
    print("- 显示实时价格和Sparkline趋势")
    print("=" * 60)
    print("访问地址: http://localhost:5001")
    print("=" * 60)
    
    # 先加载一次数据
    load_latest_data()
    
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)


if __name__ == '__main__':
    main()
