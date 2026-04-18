"""检查p2605的交易模式"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== p2605 交易记录 ===")
cursor.execute('''
    SELECT action, price, volume, pos_after, trade_datetime
    FROM trade_records 
    WHERE symbol = 'p2605' AND trade_date = '20260417'
    ORDER BY id
''')

for row in cursor.fetchall():
    print(f"{row[4]} | {row[0]} | 价格={row[1]} | 持仓={row[3]}")

conn.close()
