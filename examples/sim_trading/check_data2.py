"""检查K线数据和交易日志"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

output = []

# 检查K线数据日期范围
output.append('=== K线数据日期范围 ===')
cursor.execute('''
    SELECT symbol, MIN(datetime), MAX(datetime), COUNT(*) 
    FROM dbbardata 
    GROUP BY symbol
''')
for row in cursor.fetchall():
    output.append(f'{row[0]}: {row[1]} ~ {row[2]}, 共{row[3]}条')

# 检查今天的K线数据
today = datetime.now().strftime('%Y-%m-%d')
output.append(f'\n=== 今天({today})的K线数据 ===')
cursor.execute('''
    SELECT symbol, COUNT(*) 
    FROM dbbardata 
    WHERE datetime >= ?
    GROUP BY symbol
''', (today,))
rows = cursor.fetchall()
if rows:
    for row in rows:
        output.append(f'{row[0]}: {row[1]}条')
else:
    output.append('今天没有K线数据！')

# 检查最新的K线数据
output.append('\n=== 最新K线数据 ===')
cursor.execute('''
    SELECT symbol, datetime, close_price
    FROM dbbardata 
    ORDER BY datetime DESC
    LIMIT 5
''')
for row in cursor.fetchall():
    output.append(f'{row[0]}: {row[1]} close={row[2]}')

# 检查trade_records
output.append('\n=== 交易记录 ===')
cursor.execute('SELECT COUNT(*) FROM trade_records')
output.append(f'总记录数: {cursor.fetchone()[0]}')

conn.close()

# 写入文件
with open('d:/trading/vnpy/examples/sim_trading/data_check_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print('Done')
