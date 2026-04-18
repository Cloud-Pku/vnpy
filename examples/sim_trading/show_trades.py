"""查询今日交易记录"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print('=== 今日交易记录 ===')
cursor.execute('''
    SELECT strategy_name, symbol, action, direction, offset, price, volume, pos_after, trade_datetime
    FROM trade_records
    WHERE trade_date = '20260417'
    ORDER BY trade_datetime
''')
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'{row[8]} | {row[1]} | {row[2]} | {row[3]}{row[4]} | 价格={row[5]} | 数量={row[6]} | 持仓={row[7]}')
else:
    print('暂无交易记录')

conn.close()
