"""检查当前持仓情况"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== 各品种最新交易记录及持仓 ===\n")

for symbol in ['rb2605', 'i2605', 'MA605', 'SA605', 'p2605']:
    # 查询最新交易记录
    cursor.execute('''
        SELECT action, price, volume, pos_after, trade_datetime
        FROM trade_records 
        WHERE symbol = ? AND trade_date = '20260417'
        ORDER BY id DESC
        LIMIT 3
    ''', (symbol,))
    
    rows = cursor.fetchall()
    if rows:
        print(f"【{symbol}】")
        for row in rows:
            print(f"  {row[4]} | {row[0]} | 价格={row[1]} | 持仓={row[3]}")
        print()

print("=== 各品种当前持仓统计 ===")
cursor.execute('''
    SELECT symbol, pos_after, trade_datetime
    FROM trade_records 
    WHERE trade_date = '20260417'
    AND id IN (
        SELECT MAX(id) 
        FROM trade_records 
        WHERE trade_date = '20260417'
        GROUP BY symbol
    )
''')

for row in cursor.fetchall():
    print(f"{row[0]}: 持仓={row[1]} | {row[2]}")

conn.close()
