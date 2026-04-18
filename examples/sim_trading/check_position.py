"""查询SimNow账户实际持仓"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')

# 1. 从数据库查询各品种最新持仓
print("=== 数据库记录的最新持仓 ===")
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

for symbol in ['rb2605', 'i2605', 'MA605', 'SA605', 'p2605']:
    cursor.execute('''
        SELECT symbol, pos_after, trade_datetime, action
        FROM trade_records 
        WHERE symbol = ? AND trade_date = '20260417'
        ORDER BY id DESC
        LIMIT 1
    ''', (symbol,))
    row = cursor.fetchone()
    if row:
        print(f"{row[0]}: 持仓={row[1]} | {row[2]} | {row[3]}")
    else:
        print(f"{symbol}: 无记录")

conn.close()

# 2. 检查vn.py持仓表（如果有）
print("\n=== vn.py持仓表 ===")
try:
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%posi%'")
    tables = cursor.fetchall()
    print(f"持仓相关表: {tables}")
    
    for table in tables:
        cursor.execute(f"SELECT * FROM {table[0]} LIMIT 10")
        rows = cursor.fetchall()
        print(f"\n{table[0]}:")
        for row in rows:
            print(f"  {row}")
    conn.close()
except Exception as e:
    print(f"查询持仓表失败: {e}")
