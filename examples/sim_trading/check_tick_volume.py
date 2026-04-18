"""检查Tick数据的成交量变化"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# 检查是否有tick数据表
print("=== 检查数据库表结构 ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print(f"数据库表: {tables}")

# 检查dbbardata表的volume字段分布
print("\n=== i2605 volume分布统计 ===")
cursor.execute('''
    SELECT 
        CASE 
            WHEN volume < 100 THEN '0-100'
            WHEN volume < 500 THEN '100-500'
            WHEN volume < 1000 THEN '500-1000'
            WHEN volume < 5000 THEN '1000-5000'
            WHEN volume < 20000 THEN '5000-20000'
            ELSE '20000+'
        END as volume_range,
        COUNT(*) as count
    FROM dbbardata 
    WHERE symbol = 'i2605'
    GROUP BY volume_range
    ORDER BY MIN(volume)
''')
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} 条")

print("\n=== p2605 volume分布统计 ===")
cursor.execute('''
    SELECT 
        CASE 
            WHEN volume < 100 THEN '0-100'
            WHEN volume < 500 THEN '100-500'
            WHEN volume < 1000 THEN '500-1000'
            WHEN volume < 5000 THEN '1000-5000'
            WHEN volume < 20000 THEN '5000-20000'
            ELSE '20000+'
        END as volume_range,
        COUNT(*) as count
    FROM dbbardata 
    WHERE symbol = 'p2605'
    GROUP BY volume_range
    ORDER BY MIN(volume)
''')
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} 条")

# 检查15:31这条数据的特征
print("\n=== 15:31异常K线特征 ===")
cursor.execute('''
    SELECT datetime, open_price, high_price, low_price, close_price, volume, exchange
    FROM dbbardata 
    WHERE (symbol = 'i2605' OR symbol = 'p2605') AND volume > 20000
    ORDER BY symbol, datetime
''')
for row in cursor.fetchall():
    ohlc_same = (row[1] == row[2] == row[3] == row[4])
    print(f"{row[0]} | {row[6]} | OHLC相同={ohlc_same} | V={row[5]}")

conn.close()
