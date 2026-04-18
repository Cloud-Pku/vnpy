"""检查Tick数据表的内容"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# 检查dbtickdata表结构
print("=== dbtickdata 表结构 ===")
cursor.execute("PRAGMA table_info(dbtickdata)")
for row in cursor.fetchall():
    print(f"  {row[1]}: {row[2]}")

# 检查i2605在15:30左右的tick数据
print("\n=== i2605 15:30左右的Tick数据 ===")
try:
    cursor.execute('''
        SELECT datetime, last_price, volume, turnover
        FROM dbtickdata 
        WHERE symbol = 'i2605' AND datetime >= '2026-04-17 15:29:00' AND datetime <= '2026-04-17 15:32:00'
        ORDER BY datetime
        LIMIT 20
    ''')
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"{row[0]} | 价格={row[1]} | 成交量={row[2]} | 成交额={row[3]}")
    else:
        print("  无数据")
except Exception as e:
    print(f"  查询失败: {e}")

# 检查p2605在15:30左右的tick数据
print("\n=== p2605 15:30左右的Tick数据 ===")
try:
    cursor.execute('''
        SELECT datetime, last_price, volume, turnover
        FROM dbtickdata 
        WHERE symbol = 'p2605' AND datetime >= '2026-04-17 15:29:00' AND datetime <= '2026-04-17 15:32:00'
        ORDER BY datetime
        LIMIT 20
    ''')
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"{row[0]} | 价格={row[1]} | 成交量={row[2]} | 成交额={row[3]}")
    else:
        print("  无数据")
except Exception as e:
    print(f"  查询失败: {e}")

# 统计每个品种的tick数量
print("\n=== 各品种Tick数据数量 ===")
cursor.execute('''
    SELECT symbol, COUNT(*) 
    FROM dbtickdata 
    WHERE symbol IN ('i2605', 'p2605', 'rb2605', 'MA605', 'SA605')
    GROUP BY symbol
''')
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} 条")

conn.close()
