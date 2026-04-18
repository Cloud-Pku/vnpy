"""检查K线数据和交易日志"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# 检查K线数据日期范围
print('=== K线数据日期范围 ===')
cursor.execute('''
    SELECT symbol, MIN(datetime), MAX(datetime), COUNT(*) 
    FROM dbbardata 
    GROUP BY symbol
''')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]} ~ {row[2]}, 共{row[3]}条')

# 检查今天的K线数据
today = datetime.now().strftime('%Y-%m-%d')
print(f'\n=== 今天({today})的K线数据 ===')
cursor.execute('''
    SELECT symbol, COUNT(*) 
    FROM dbbardata 
    WHERE datetime >= ?
    GROUP BY symbol
''', (today,))
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'{row[0]}: {row[1]}条')
else:
    print('今天没有K线数据！')

# 检查最新的K线数据
print('\n=== 最新K线数据 ===')
cursor.execute('''
    SELECT symbol, datetime, close_price
    FROM dbbardata 
    ORDER BY datetime DESC
    LIMIT 5
''')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]} close={row[2]}')

# 检查trade_records
print('\n=== 交易记录 ===')
cursor.execute('SELECT COUNT(*) FROM trade_records')
print(f'总记录数: {cursor.fetchone()[0]}')

conn.close()
