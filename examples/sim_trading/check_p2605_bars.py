"""检查p2605的K线数据"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print(f"当前日期: {datetime.now().strftime('%Y-%m-%d')}")

# 查询p2605的最新K线数据
print("\n=== p2605 最新10条K线 ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume, exchange
    FROM dbbardata 
    WHERE symbol = 'p2605'
    ORDER BY datetime DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    print(f"{row[0]} | O={row[1]:.1f} H={row[2]:.1f} L={row[3]:.1f} C={row[4]:.1f} V={row[5]} | {row[6]}")

# 查询今天的K线数量
print("\n=== 今日K线统计 ===")
today = datetime.now().strftime("%Y-%m-%d")
for symbol in ['p2605', 'rb2605', 'i2605', 'MA605', 'SA605']:
    cursor.execute('''
        SELECT COUNT(*), MIN(datetime), MAX(datetime)
        FROM dbbardata 
        WHERE symbol = ? AND datetime >= ?
    ''', (symbol, today))
    row = cursor.fetchone()
    print(f"{symbol}: {row[0]}条 | {row[1]} ~ {row[2]}")

conn.close()
