"""
Tick实时可视化工具
- 显示每只期货的Tick价格随时间变化折线图
- 扣除非交易时段
- 标记策略交易动作（买入/卖出/持仓变化）
- 支持多品种对比显示
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# 配置
LOG_PATH = Path.home() / ".vntrader" / "log"
DB_PATH = Path.home() / ".vntrader" / "database.db"
OUTPUT_PATH = Path("tick_analysis.html")

# 监控品种
MONITORED_SYMBOLS = [
    "rb2605.SHFE",
    "i2605.DCE", 
    "MA605.CZCE",
    "SA605.CZCE",
    "p2605.DCE",
]

# 交易时段配置
TRADING_SESSIONS = [
    (time(9, 0), time(11, 30)),   # 上午盘
    (time(13, 30), time(15, 0)),  # 下午盘
    (time(21, 0), time(23, 59)),  # 夜盘开始
    (time(0, 0), time(2, 30)),    # 夜盘结束（跨天）
]


@dataclass
class TickData:
    """Tick数据"""
    datetime: datetime
    symbol: str
    price: float
    volume: int


@dataclass
class TradeAction:
    """交易动作"""
    datetime: datetime
    symbol: str
    action: str  # BUY/SELL/COVER/SHORT
    price: float
    volume: int
    pos_before: int
    pos_after: int


def is_trading_time(dt: datetime) -> bool:
    """检查是否在交易时段内"""
    t = dt.time()
    
    # 上午盘 09:00-11:30
    if time(9, 0) <= t <= time(11, 30):
        return True
    
    # 下午盘 13:30-15:00
    if time(13, 30) <= t <= time(15, 0):
        return True
    
    # 夜盘 21:00-23:59 或 00:00-02:30
    if time(21, 0) <= t <= time(23, 59):
        return True
    if time(0, 0) <= t <= time(2, 30):
        return True
    
    return False


def parse_log_for_ticks(date_str: str = None) -> Dict[str, List[TickData]]:
    """从日志文件解析Tick数据"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    log_file = LOG_PATH / f"vt_{date_str}.log"
    if not log_file.exists():
        print(f"日志文件不存在: {log_file}")
        return {}
    
    # Tick数据正则匹配
    tick_pattern = re.compile(
        r'\[(?:Tick|Tick诊断)\]\s+(?P<symbol>\S+)\s+\|\s+第\d+个\s+\|\s+(?:最新价=)?(?P<price>[\d.]+)'
        r'.*?时间=(?P<time>[\d\-:\s+]+)'
    )
    
    ticks_by_symbol: Dict[str, List[TickData]] = {s: [] for s in MONITORED_SYMBOLS}
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                match = tick_pattern.search(line)
                if match:
                    symbol = match.group('symbol')
                    if symbol not in ticks_by_symbol:
                        continue
                    
                    try:
                        price = float(match.group('price'))
                        time_str = match.group('time').strip()
                        
                        # 解析时间
                        dt = parse_log_datetime(time_str)
                        if dt and is_trading_time(dt):
                            ticks_by_symbol[symbol].append(TickData(
                                datetime=dt,
                                symbol=symbol,
                                price=price,
                                volume=0
                            ))
                    except (ValueError, AttributeError):
                        continue
    except Exception as e:
        print(f"解析日志错误: {e}")
    
    # 排序
    for symbol in ticks_by_symbol:
        ticks_by_symbol[symbol].sort(key=lambda x: x.datetime)
    
    return ticks_by_symbol


def parse_log_datetime(time_str: str) -> Optional[datetime]:
    """解析日志中的时间字符串"""
    formats = [
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ]
    
    # 清理字符串
    time_str = time_str.strip()
    if time_str.endswith('+08:00'):
        time_str = time_str[:-6]
    
    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    
    return None


def parse_log_for_actions(date_str: str = None) -> List[TradeAction]:
    """从日志解析交易动作"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    log_file = LOG_PATH / f"vt_{date_str}.log"
    if not log_file.exists():
        return []
    
    actions = []
    
    # 匹配持仓变化日志
    pos_pattern = re.compile(
        r'\[运行中\].*?持仓=(?P<pos>-?\d+)'
    )
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # 查找所有带时间的持仓记录
        lines = content.split('\n')
        prev_pos = {}
        
        for line in lines:
            # 提取时间
            time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if not time_match:
                continue
            
            dt = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M:%S")
            
            # 查找持仓变化
            pos_match = pos_pattern.search(line)
            if pos_match:
                pos = int(pos_match.group('pos'))
                # 这里简化处理，实际应该从策略日志中提取具体动作
                
    except Exception as e:
        print(f"解析交易动作错误: {e}")
    
    return actions


def get_bar_data_from_db(symbol: str, date_str: str = None) -> pd.DataFrame:
    """从数据库获取K线数据作为Tick的聚合"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    if not DB_PATH.exists():
        return pd.DataFrame()
    
    try:
        parts = symbol.split('.')
        if len(parts) != 2:
            return pd.DataFrame()
        
        sym, exchange = parts
        
        conn = sqlite3.connect(str(DB_PATH))
        
        query = """
            SELECT datetime, open_price, high_price, low_price, close_price, volume
            FROM dbbardata
            WHERE symbol = ? AND exchange = ? AND interval = '1m'
            ORDER BY datetime
        """
        
        df = pd.read_sql_query(query, conn, params=(sym, exchange))
        conn.close()
        
        if df.empty:
            return df
        
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['symbol'] = symbol
        
        # 过滤非交易时段
        df = df[df['datetime'].apply(lambda x: is_trading_time(x))]
        
        return df
    except Exception as e:
        print(f"查询数据库错误: {e}")
        return pd.DataFrame()


def create_tick_chart(symbol: str, ticks: List[TickData], bars_df: pd.DataFrame) -> go.Figure:
    """创建单个品种的Tick走势图"""
    if not ticks and bars_df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="暂无数据",
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=20)
        )
        return fig
    
    fig = go.Figure()
    
    # 使用K线数据作为主要价格线（更稳定）
    if not bars_df.empty:
        fig.add_trace(go.Scatter(
            x=bars_df['datetime'],
            y=bars_df['close_price'],
            mode='lines',
            name='收盘价',
            line=dict(width=1.5, color='#00A6D6'),
            hovertemplate='时间: %{x}<br>价格: %{y:.1f}<extra></extra>'
        ))
        
        # 添加高低价区域
        fig.add_trace(go.Scatter(
            x=bars_df['datetime'].tolist() + bars_df['datetime'].tolist()[::-1],
            y=bars_df['high_price'].tolist() + bars_df['low_price'].tolist()[::-1],
            fill='toself',
            fillcolor='rgba(0, 166, 214, 0.1)',
            line=dict(color='rgba(0,0,0,0)'),
            name='高低区间',
            hoverinfo='skip'
        ))
    
    # 添加Tick散点（采样显示，避免过多）
    if ticks:
        tick_df = pd.DataFrame([{
            'datetime': t.datetime,
            'price': t.price
        } for t in ticks])
        
        # 每10个Tick采样1个，避免图表过于密集
        tick_df = tick_df.iloc[::10]
        
        fig.add_trace(go.Scatter(
            x=tick_df['datetime'],
            y=tick_df['price'],
            mode='markers',
            name='Tick采样',
            marker=dict(
                size=3,
                color='rgba(255, 255, 255, 0.5)',
            ),
            hovertemplate='时间: %{x}<br>Tick: %{y:.1f}<extra></extra>'
        ))
    
    # 标记交易时段
    add_trading_session_shapes(fig, bars_df)
    
    fig.update_layout(
        title=dict(
            text=f'{symbol} - Tick价格走势',
            x=0.5,
            font=dict(size=16)
        ),
        template='plotly_dark',
        height=400,
        xaxis=dict(
            title='时间',
            showgrid=True,
            gridcolor='rgba(255,255,255,0.1)'
        ),
        yaxis=dict(
            title='价格',
            showgrid=True,
            gridcolor='rgba(255,255,255,0.1)'
        ),
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        )
    )
    
    return fig


def add_trading_session_shapes(fig: go.Figure, df: pd.DataFrame):
    """添加交易时段标记"""
    if df.empty:
        return
    
    # 获取日期
    dates = df['datetime'].dt.date.unique()
    
    shapes = []
    for date in dates:
        # 非交易时段背景（灰色）
        # 11:30-13:30 午休
        noon_start = datetime.combine(date, time(11, 30))
        noon_end = datetime.combine(date, time(13, 30))
        
        shapes.append(dict(
            type='rect',
            xref='x',
            yref='paper',
            x0=noon_start,
            y0=0,
            x1=noon_end,
            y1=1,
            fillcolor='rgba(128, 128, 128, 0.1)',
            line=dict(width=0),
            layer='below'
        ))
    
    fig.update_layout(shapes=shapes)


def create_multi_symbol_chart(bars_data: Dict[str, pd.DataFrame]) -> go.Figure:
    """创建多品种对比图"""
    n_symbols = len([s for s in bars_data if not bars_data[s].empty])
    
    if n_symbols == 0:
        fig = go.Figure()
        fig.add_annotation(text="暂无数据", xref="paper", yref="paper", showarrow=False)
        return fig
    
    fig = make_subplots(
        rows=n_symbols,
        cols=1,
        shared_xaxes=True,
        subplot_titles=list(bars_data.keys()),
        vertical_spacing=0.05
    )
    
    row = 1
    for symbol, df in bars_data.items():
        if df.empty:
            continue
        
        # 标准化价格（以第一个价格为基准100）
        base_price = df['close_price'].iloc[0]
        normalized = (df['close_price'] / base_price - 1) * 100
        
        fig.add_trace(
            go.Scatter(
                x=df['datetime'],
                y=normalized,
                mode='lines',
                name=symbol,
                line=dict(width=1.5),
                hovertemplate='%{x}<br>涨跌幅: %{y:.2f}%<extra></extra>'
            ),
            row=row, col=1
        )
        
        row += 1
    
    fig.update_layout(
        title=dict(
            text='多品种价格走势对比（标准化）',
            x=0.5
        ),
        template='plotly_dark',
        height=200 * n_symbols,
        showlegend=False,
        hovermode='x unified'
    )
    
    return fig


def generate_report(date_str: str = None):
    """生成可视化报告"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    print(f"正在生成 {date_str} 的Tick分析报告...")
    
    # 获取数据
    ticks_data = parse_log_for_ticks(date_str)
    bars_data = {}
    
    for symbol in MONITORED_SYMBOLS:
        bars_data[symbol] = get_bar_data_from_db(symbol, date_str)
    
    # 创建图表
    figures = []
    
    # 1. 多品种对比图
    fig_multi = create_multi_symbol_chart(bars_data)
    figures.append(('多品种对比', fig_multi))
    
    # 2. 各品种详细图
    for symbol in MONITORED_SYMBOLS:
        fig = create_tick_chart(symbol, ticks_data.get(symbol, []), bars_data[symbol])
        figures.append((symbol, fig))
    
    # 组合成HTML
    html_parts = [
        '<!DOCTYPE html>',
        '<html>',
        '<head>',
        '<meta charset="utf-8">',
        '<title>Tick分析报告</title>',
        '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>',
        '<style>',
        'body { font-family: Arial, sans-serif; background: #1a1a2e; color: #fff; margin: 0; padding: 20px; }',
        'h1 { text-align: center; color: #00d4ff; }',
        'h2 { color: #00d4ff; margin-top: 30px; border-bottom: 2px solid #00d4ff; padding-bottom: 10px; }',
        '.summary { background: #16213e; padding: 20px; border-radius: 10px; margin: 20px 0; }',
        '.summary-item { display: inline-block; margin: 10px 20px; }',
        '.summary-label { color: #888; font-size: 12px; }',
        '.summary-value { font-size: 24px; font-weight: bold; color: #00d4ff; }',
        '</style>',
        '</head>',
        '<body>',
        f'<h1>📈 Tick实时分析报告 - {date_str}</h1>',
    ]
    
    # 添加汇总信息
    total_ticks = sum(len(ticks) for ticks in ticks_data.values())
    total_bars = sum(len(df) for df in bars_data.values())
    
    html_parts.append('<div class="summary">')
    html_parts.append(f'<div class="summary-item"><div class="summary-label">总Tick数</div><div class="summary-value">{total_ticks}</div></div>')
    html_parts.append(f'<div class="summary-item"><div class="summary-label">总K线数</div><div class="summary-value">{total_bars}</div></div>')
    html_parts.append(f'<div class="summary-item"><div class="summary-label">监控品种</div><div class="summary-value">{len(MONITORED_SYMBOLS)}</div></div>')
    html_parts.append('</div>')
    
    # 添加图表
    for title, fig in figures:
        html_parts.append(f'<h2>{title}</h2>')
        html_parts.append(fig.to_html(full_html=False, include_plotlyjs=False))
    
    html_parts.extend([
        '</body>',
        '</html>'
    ])
    
    # 保存
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))
    
    print(f"报告已生成: {OUTPUT_PATH.absolute()}")
    return OUTPUT_PATH


if __name__ == '__main__':
    import sys
    
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    report_path = generate_report(date_str)
    print(f"请在浏览器中打开: {report_path}")
