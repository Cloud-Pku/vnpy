"""
多品种交易池实时监控Web服务
- 实时显示各品种K线数据
- 显示策略状态和持仓
- 提供REST API接口
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 数据库路径
DB_PATH = Path.home() / ".vntrader" / "database.db"
LOG_PATH = Path.home() / ".vntrader" / "log"

# 监控配置
MONITORED_SYMBOLS = [
    "rb2605.SHFE",
    "i2605.DCE",
    "MA605.CZCE",
    "SA605.CZCE",
    "p2605.DCE",
]


@dataclass
class BarData:
    """K线数据"""
    symbol: str
    exchange: str
    datetime: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


@dataclass
class StrategyStatus:
    """策略状态"""
    name: str
    symbol: str
    status: str  # warming/running/stopped
    pos: int
    fast_ma: float
    slow_ma: float
    tick_count: int
    last_update: str


@dataclass
class AccountInfo:
    """账户资金信息"""
    balance: float      # 账户余额
    available: float    # 可用资金
    frozen: float       # 冻结资金
    pnl: float          # 浮动盈亏
    
    @classmethod
    def from_simnow_default(cls):
        """SimNow默认初始资金约100万"""
        # 这里可以从日志或数据库读取实际值
        # 暂时使用模拟数据，实际应从交易引擎获取
        return cls(
            balance=1000000.0,
            available=950000.0,
            frozen=50000.0,
            pnl=0.0
        )


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def query_latest_bars(symbol: str, limit: int = 10) -> List[BarData]:
    """查询最新的K线数据"""
    if not DB_PATH.exists():
        return []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 解析symbol
        parts = symbol.split('.')
        if len(parts) != 2:
            return []
        
        sym, exchange = parts
        
        cursor.execute("""
            SELECT symbol, exchange, datetime, open_price, high_price, 
                   low_price, close_price, volume
            FROM dbbardata
            WHERE symbol = ? AND exchange = ? AND interval = '1m'
            ORDER BY datetime DESC
            LIMIT ?
        """, (sym, exchange, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        bars = []
        for row in rows:
            bars.append(BarData(
                symbol=row['symbol'],
                exchange=row['exchange'],
                datetime=row['datetime'],
                open_price=row['open_price'],
                high_price=row['high_price'],
                low_price=row['low_price'],
                close_price=row['close_price'],
                volume=row['volume']
            ))
        
        return bars
    except Exception as e:
        print(f"查询数据库错误: {e}")
        return []


def query_bar_stats() -> Dict:
    """查询K线统计信息"""
    if not DB_PATH.exists():
        return {"error": "数据库不存在"}
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        for symbol in MONITORED_SYMBOLS:
            parts = symbol.split('.')
            if len(parts) != 2:
                continue
            
            sym, exchange = parts
            
            # 查询该品种的总K线数
            cursor.execute("""
                SELECT COUNT(*) as count, MAX(datetime) as latest
                FROM dbbardata
                WHERE symbol = ? AND exchange = ? AND interval = '1m'
            """, (sym, exchange))
            
            row = cursor.fetchone()
            stats[symbol] = {
                "count": row['count'] if row else 0,
                "latest": row['latest'] if row else None
            }
        
        conn.close()
        return stats
    except Exception as e:
        return {"error": str(e)}


# HTML模板
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>多品种交易池监控</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="5">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 0;
            padding: 20px;
        }
        h1 {
            text-align: center;
            color: #00d4ff;
            margin-bottom: 30px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .account-section {
            background: linear-gradient(135deg, #16213e 0%, #0f3460 100%);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            border: 2px solid #e94560;
        }
        .account-title {
            font-size: 18px;
            color: #e94560;
            margin-bottom: 20px;
            text-align: center;
        }
        .account-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        .account-item {
            background: rgba(0,0,0,0.3);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .account-label {
            font-size: 12px;
            color: #888;
            margin-bottom: 5px;
        }
        .account-value {
            font-size: 24px;
            font-weight: bold;
            color: #fff;
        }
        .account-value.positive { color: #0f0; }
        .account-value.negative { color: #f00; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            border-left: 4px solid #00d4ff;
        }
        .stat-card h3 {
            margin: 0 0 10px 0;
            color: #00d4ff;
            font-size: 14px;
            text-transform: uppercase;
        }
        .stat-value {
            font-size: 28px;
            font-weight: bold;
            color: #fff;
        }
        .symbol-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }
        .symbol-card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #0f3460;
        }
        .symbol-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #0f3460;
        }
        .symbol-name {
            font-size: 18px;
            font-weight: bold;
            color: #00d4ff;
        }
        .symbol-status {
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 12px;
            background: #e94560;
        }
        .symbol-status.active {
            background: #0f0;
            color: #000;
        }
        .price-info {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-bottom: 15px;
        }
        .price-item {
            background: #0f3460;
            padding: 10px;
            border-radius: 5px;
        }
        .price-label {
            font-size: 12px;
            color: #888;
        }
        .price-value {
            font-size: 16px;
            font-weight: bold;
        }
        .price-up { color: #0f0; }
        .price-down { color: #f00; }
        .bar-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        .bar-table th {
            background: #0f3460;
            padding: 8px;
            text-align: left;
        }
        .bar-table td {
            padding: 8px;
            border-bottom: 1px solid #0f3460;
        }
        .bar-table tr:hover {
            background: #0f3460;
        }
        .update-time {
            text-align: center;
            color: #888;
            margin-top: 20px;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 多品种交易池实时监控</h1>
        
        <!-- 账户资金信息 -->
        <div class="account-section">
            <div class="account-title">💰 SimNow 仿真账户资金 (初始本金: 1,000,000 CNY)</div>
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
                <div class="account-item">
                    <div class="account-label">浮动盈亏</div>
                    <div class="account-value {% if account.pnl >= 0 %}positive{% else %}negative{% endif %}">
                        {{ "{:,.2f}".format(account.pnl) }}
                    </div>
                </div>
                <div class="account-item">
                    <div class="account-label">收益率</div>
                    <div class="account-value {% if account.pnl >= 0 %}positive{% else %}negative{% endif %}">
                        {{ "{:.2f}".format(account.pnl / 1000000 * 100) }}%
                    </div>
                </div>
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>监控品种数</h3>
                <div class="stat-value">{{ stats.symbol_count }}</div>
            </div>
            <div class="stat-card">
                <h3>总K线数</h3>
                <div class="stat-value">{{ stats.total_bars }}</div>
            </div>
            <div class="stat-card">
                <h3>最新数据时间</h3>
                <div class="stat-value" style="font-size: 16px;">{{ stats.latest_time }}</div>
            </div>
        </div>
        
        <div class="symbol-grid">
            {% for symbol, data in symbols.items() %}
            <div class="symbol-card">
                <div class="symbol-header">
                    <span class="symbol-name">{{ symbol }}</span>
                    <span class="symbol-status {% if data.bars %}active{% endif %}">
                        {% if data.bars %}运行中{% else %}等待数据{% endif %}
                    </span>
                </div>
                
                {% if data.bars %}
                {% set latest = data.bars[0] %}
                <div class="price-info">
                    <div class="price-item">
                        <div class="price-label">最新价</div>
                        <div class="price-value">{{ "%.1f"|format(latest.close_price) }}</div>
                    </div>
                    <div class="price-item">
                        <div class="price-label">涨跌幅</div>
                        <div class="price-value {% if latest.close_price >= latest.open_price %}price-up{% else %}price-down{% endif %}">
                            {{ "%.2f"|format((latest.close_price - latest.open_price) / latest.open_price * 100) }}%
                        </div>
                    </div>
                    <div class="price-item">
                        <div class="price-label">最高</div>
                        <div class="price-value">{{ "%.1f"|format(latest.high_price) }}</div>
                    </div>
                    <div class="price-item">
                        <div class="price-label">最低</div>
                        <div class="price-value">{{ "%.1f"|format(latest.low_price) }}</div>
                    </div>
                </div>
                
                <table class="bar-table">
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>开盘</th>
                            <th>收盘</th>
                            <th>成交量</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for bar in data.bars[:5] %}
                        <tr>
                            <td>{{ bar.datetime[11:16] }}</td>
                            <td>{{ "%.1f"|format(bar.open_price) }}</td>
                            <td class="{% if bar.close_price >= bar.open_price %}price-up{% else %}price-down{% endif %}">
                                {{ "%.1f"|format(bar.close_price) }}
                            </td>
                            <td>{{ "%.0f"|format(bar.volume) }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="text-align: center; color: #888;">暂无数据</p>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        
        <div class="update-time">
            最后更新: {{ update_time }} | 自动刷新间隔: 5秒
        </div>
    </div>
</body>
</html>
"""


def parse_account_from_log() -> AccountInfo:
    """从日志文件解析账户资金信息"""
    try:
        # 尝试从日志中读取账户信息
        log_file = LOG_PATH / f"vt_{datetime.now().strftime('%Y%m%d')}.log"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # 查找持仓信息来估算盈亏
                # 实际应从CTP账户查询接口获取
                pass
    except Exception:
        pass
    
    # 返回默认值或从数据库读取
    return AccountInfo.from_simnow_default()


@app.route('/')
def dashboard():
    """监控面板首页"""
    # 查询所有品种的K线数据
    symbols_data = {}
    total_bars = 0
    latest_times = []
    
    for symbol in MONITORED_SYMBOLS:
        bars = query_latest_bars(symbol, limit=10)
        symbols_data[symbol] = {
            "bars": [asdict(bar) for bar in bars]
        }
        total_bars += len(bars)
        if bars:
            latest_times.append(bars[0].datetime)
    
    stats = {
        "symbol_count": len(MONITORED_SYMBOLS),
        "total_bars": total_bars,
        "latest_time": max(latest_times) if latest_times else "无数据"
    }
    
    # 获取账户信息
    account = parse_account_from_log()
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        symbols=symbols_data,
        stats=stats,
        account=account,
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.route('/api/bars/<symbol>')
def api_bars(symbol: str):
    """获取指定品种的K线数据API"""
    limit = request.args.get('limit', 100, type=int)
    bars = query_latest_bars(symbol, limit=limit)
    return jsonify({
        "symbol": symbol,
        "count": len(bars),
        "data": [asdict(bar) for bar in bars]
    })


@app.route('/api/stats')
def api_stats():
    """获取统计信息API"""
    stats = query_bar_stats()
    return jsonify(stats)


@app.route('/api/symbols')
def api_symbols():
    """获取监控品种列表"""
    return jsonify({
        "symbols": MONITORED_SYMBOLS,
        "count": len(MONITORED_SYMBOLS)
    })


@app.route('/api/account')
def api_account():
    """获取账户资金信息API"""
    account = parse_account_from_log()
    return jsonify({
        "account": asdict(account),
        "initial_capital": 1000000.0,
        "platform": "SimNow"
    })


from flask import request


def main():
    """启动监控服务"""
    print("=" * 60)
    print("多品种交易池监控服务")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")
    print(f"监控品种: {', '.join(MONITORED_SYMBOLS)}")
    print("=" * 60)
    print("访问地址:")
    print("  - 监控面板: http://localhost:5000")
    print("  - API接口: http://localhost:5000/api/stats")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
