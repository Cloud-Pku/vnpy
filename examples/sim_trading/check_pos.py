"""检查p2605的完整交易序列"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== p2605 完整交易序列 ===")
cursor.execute('''
    SELECT trade_datetime, action, direction, offset, price, volume, pos_after
    FROM trade_records 
    WHERE symbol = 'p2605' AND trade_date = '20260417'
    ORDER BY trade_datetime
''')

expected_pos = 0
for row in cursor.fetchall():
    dt, action, direction, offset, price, volume, pos_after = row
    
    # 计算期望持仓
    if action == 'BUY':
        expected_pos += volume
    elif action == 'SHORT':
        expected_pos -= volume
    elif action == 'SELL':
        expected_pos -= volume  # 平多
    elif action == 'COVER':
        expected_pos += volume  # 平空
    
    match = "✅" if pos_after == expected_pos else f"❌ 期望{expected_pos}"
    print(f"{dt} | {action:5} | {direction:5} | {offset:10} | 价格={price:.1f} | 持仓={pos_after} {match}")

conn.close()
