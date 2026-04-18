"""检查i2605和p2605的成交量异常"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== i2605 成交量最大的10根K线 ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume
    FROM dbbardata 
    WHERE symbol = 'i2605'
    ORDER BY volume DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    print(f"{row[0]} | O={row[1]} H={row[2]} L={row[3]} C={row[4]} | V={row[5]}")

print("\n=== p2605 成交量最大的10根K线 ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume
    FROM dbbardata 
    WHERE symbol = 'p2605'
    ORDER BY volume DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    print(f"{row[0]} | O={row[1]} H={row[2]} L={row[3]} C={row[4]} | V={row[5]}")

print("\n=== MA605 成交量最大的10根K线（对比） ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume
    FROM dbbardata 
    WHERE symbol = 'MA605'
    ORDER BY volume DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    print(f"{row[0]} | O={row[1]} H={row[2]} L={row[3]} C={row[4]} | V={row[5]}")

# 检查是否有重复数据
print("\n=== 检查i2605 15:31的数据 ===")
cursor.execute('''
    SELECT datetime, volume, exchange
    FROM dbbardata 
    WHERE symbol = 'i2605' AND datetime LIKE '2026-04-17 15:31%'
    ORDER BY datetime
''')
for row in cursor.fetchall():
    print(f"{row[0]} | V={row[1]} | {row[2]}")

conn.close()
