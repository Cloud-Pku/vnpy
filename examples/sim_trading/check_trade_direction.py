"""检查成交方向"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print('=== 检查成交方向分布 ===')
cursor.execute('''
    SELECT action, direction, offset, COUNT(*) 
    FROM trade_records 
    WHERE trade_date = '20260417'
    GROUP BY action, direction, offset
''')
for row in cursor.fetchall():
    print(f'action={row[0]}, direction={row[1]}, offset={row[2]}: {row[3]}条')

print('\n=== 买入记录示例 ===')
cursor.execute('''
    SELECT trade_datetime, symbol, action, direction, offset, price, pos_after
    FROM trade_records 
    WHERE trade_date = '20260417' AND (action='BUY' OR action='COVER')
    LIMIT 5
''')
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'{row[0]} | {row[1]} | {row[2]} | {row[3]}{row[4]} | 价格={row[5]} | 持仓={row[6]}')
else:
    print('无买入记录')

conn.close()
