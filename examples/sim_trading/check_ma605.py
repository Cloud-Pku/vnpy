"""检查MA605的完整交易序列"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== MA605 完整交易序列 ===")
cursor.execute('''
    SELECT trade_datetime, action, direction, offset, price, volume, pos_after
    FROM trade_records 
    WHERE symbol = 'MA605' AND trade_date = '20260417'
    ORDER BY trade_datetime
''')

for row in cursor.fetchall():
    dt, action, direction, offset, price, volume, pos_after = row
    print(f"{dt} | {action:5} | {direction:5} | {offset:10} | 价格={price:.1f} | 持仓={pos_after}")

conn.close()
