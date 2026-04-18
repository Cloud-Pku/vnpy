"""检查SA605的盈亏计算详情"""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')

@dataclass
class TradeSignal:
    action: str
    price: float
    volume: int
    pos_after: int

def calculate_pnl_fixed(trades: List[TradeSignal], current_price: float, 
                        contract_multiplier: int = 20) -> Tuple[float, int]:
    """修复后的盈亏计算"""
    pos = 0
    cost = 0.0
    realized_pnl = 0.0
    
    for trade in trades:
        if trade.action == 'BUY':
            if pos >= 0:
                cost += trade.price * trade.volume
                pos += trade.volume
            else:
                avg_cost = cost / abs(pos) if pos < 0 else 0
                close_volume = min(trade.volume, abs(pos))
                realized_pnl += (avg_cost - trade.price) * close_volume * contract_multiplier
                cost_per_unit = cost / abs(pos) if pos != 0 else 0
                cost -= cost_per_unit * close_volume
                pos += trade.volume
                if pos > 0:
                    cost = trade.price * pos
                    
        elif trade.action == 'SHORT':
            if pos <= 0:
                cost += trade.price * trade.volume
                pos -= trade.volume
            else:
                avg_cost = cost / pos if pos > 0 else 0
                close_volume = min(trade.volume, pos)
                realized_pnl += (trade.price - avg_cost) * close_volume * contract_multiplier
                cost_per_unit = cost / pos if pos != 0 else 0
                cost -= cost_per_unit * close_volume
                pos -= trade.volume
                if pos < 0:
                    cost = trade.price * abs(pos)
                    
        elif trade.action == 'SELL':
            if pos > 0:
                avg_cost = cost / pos
                close_volume = min(trade.volume, pos)
                realized_pnl += (trade.price - avg_cost) * close_volume * contract_multiplier
                cost_per_unit = cost / pos
                cost -= cost_per_unit * close_volume
                pos -= trade.volume
                if pos == 0:
                    cost = 0.0
                    
        elif trade.action == 'COVER':
            if pos < 0:
                avg_cost = cost / abs(pos)
                close_volume = min(trade.volume, abs(pos))
                realized_pnl += (avg_cost - trade.price) * close_volume * contract_multiplier
                cost_per_unit = cost / abs(pos)
                cost -= cost_per_unit * close_volume
                pos += trade.volume
                if pos == 0:
                    cost = 0.0
    
    if pos > 0:
        avg_cost = cost / pos if pos > 0 else 0
        unrealized = (current_price - avg_cost) * pos * contract_multiplier
    elif pos < 0:
        avg_cost = cost / abs(pos) if pos < 0 else 0
        unrealized = (avg_cost - current_price) * abs(pos) * contract_multiplier
    else:
        unrealized = 0.0
    
    total_pnl = realized_pnl + unrealized
    return total_pnl, pos, realized_pnl, unrealized, cost

# 查询交易记录
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== SA605 交易记录 ===")
cursor.execute('''
    SELECT action, price, volume, pos_after, trade_datetime
    FROM trade_records 
    WHERE symbol = 'SA605' AND trade_date = '20260417'
    ORDER BY id
''')

trades_data = cursor.fetchall()
print(f"总交易记录数: {len(trades_data)}")
print()

# 构建交易列表
trades = []
for row in trades_data:
    trades.append(TradeSignal(action=row[0], price=row[1], volume=row[2], pos_after=row[3]))
    print(f"{row[4]} | {row[0]} | 价格={row[1]} | 持仓={row[3]}")

# 查询最新价格
cursor.execute('''
    SELECT close_price FROM dbbardata 
    WHERE symbol = 'SA605' 
    ORDER BY datetime DESC LIMIT 1
''')
latest_price = cursor.fetchone()
current_price = latest_price[0] if latest_price else 0

print(f"\n最新价格: {current_price}")

# 计算盈亏
total_pnl, pos, realized, unrealized, cost = calculate_pnl_fixed(trades, current_price, 20)

print(f"\n=== 修复后计算结果 ===")
print(f"最终持仓: {pos}")
print(f"持仓成本: {cost:.2f}")
print(f"已实现盈亏: {realized:.2f}")
print(f"浮动盈亏: {unrealized:.2f}")
print(f"总盈亏: {total_pnl:.2f}")

conn.close()
