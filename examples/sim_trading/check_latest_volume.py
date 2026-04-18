"""检查各品种最新K线的成交量"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== 各品种最新K线成交量 ===\n")

for symbol in ['rb2605', 'i2605', 'MA605', 'SA605', 'p2605']:
    cursor.execute('''
        SELECT datetime, open_price, high_price, low_price, close_price, volume
        FROM dbbardata 
        WHERE symbol = ?
        ORDER BY datetime DESC
        LIMIT 1
    ''', (symbol,))
    
    row = cursor.fetchone()
    if row:
        print(f"【{symbol}】")
        print(f"  时间: {row[0]}")
        print(f"  价格: O={row[1]} H={row[2]} L={row[3]} C={row[4]}")
        print(f"  成交量: {row[5]} 手")
        print()

conn.close()
