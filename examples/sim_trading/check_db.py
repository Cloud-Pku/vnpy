"""检查数据库交易记录"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print(f"当前日期: {datetime.now().strftime('%Y%m%d')}")

print('\n=== 所有交易记录 ===')
cursor.execute('''
    SELECT trade_date, symbol, action, price, pos_after, trade_datetime
    FROM trade_records 
    ORDER BY trade_datetime DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    print(f"{row[0]} | {row[1]} | {row[2]} | 价格={row[3]} | 持仓={row[4]} | {row[5]}")

print('\n=== 按action统计 ===')
cursor.execute('''
    SELECT action, COUNT(*) 
    FROM trade_records 
    GROUP BY action
''')
for row in cursor.fetchall():
    print(f"{row[0]}: {row[1]}条")

conn.close()
