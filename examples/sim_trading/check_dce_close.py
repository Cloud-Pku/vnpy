"""检查大商所品种收盘数据"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# 检查15:30-15:35的数据
print("=== i2605 收盘前后数据 ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume, exchange
    FROM dbbardata 
    WHERE symbol = 'i2605' AND datetime >= '2026-04-17 15:25:00' AND datetime <= '2026-04-17 15:35:00'
    ORDER BY datetime
''')
for row in cursor.fetchall():
    print(f"{row[0]} | O={row[1]} H={row[2]} L={row[3]} C={row[4]} | V={row[5]} | {row[6]}")

print("\n=== p2605 收盘前后数据 ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume, exchange
    FROM dbbardata 
    WHERE symbol = 'p2605' AND datetime >= '2026-04-17 15:25:00' AND datetime <= '2026-04-17 15:35:00'
    ORDER BY datetime
''')
for row in cursor.fetchall():
    print(f"{row[0]} | O={row[1]} H={row[2]} L={row[3]} C={row[4]} | V={row[5]} | {row[6]}")

print("\n=== rb2605(SHFE) 收盘前后数据对比 ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume, exchange
    FROM dbbardata 
    WHERE symbol = 'rb2605' AND datetime >= '2026-04-17 15:25:00' AND datetime <= '2026-04-17 15:35:00'
    ORDER BY datetime
''')
for row in cursor.fetchall():
    print(f"{row[0]} | O={row[1]} H={row[2]} L={row[3]} C={row[4]} | V={row[5]} | {row[6]}")

conn.close()
