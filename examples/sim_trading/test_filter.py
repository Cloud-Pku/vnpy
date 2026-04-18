"""测试过滤逻辑"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== 测试过滤逻辑 ===\n")

for symbol in ['i2605', 'p2605']:
    print(f"【{symbol}】")
    
    # 查询原始最新K线
    cursor.execute('''
        SELECT datetime, open_price, high_price, low_price, close_price, volume
        FROM dbbardata 
        WHERE symbol = ?
        ORDER BY datetime DESC
        LIMIT 1
    ''', (symbol,))
    
    row = cursor.fetchone()
    if row:
        dt, o, h, l, c, v = row
        is_1531 = "15:31:" in str(dt)
        ohlc_same = (o == h == l == c)
        
        print(f"  原始最新: {dt} | O={o} H={h} L={l} C={c} | V={v}")
        print(f"  是15:31: {is_1531}, OHLC相同: {ohlc_same}")
        
        if v > 10000 and ohlc_same and is_1531:
            print(f"  → 将被过滤（日汇总K线）")
            
            # 查询过滤后的最新K线
            cursor.execute('''
                SELECT datetime, open_price, high_price, low_price, close_price, volume
                FROM dbbardata 
                WHERE symbol = ? AND NOT (volume > 10000 AND open_price = high_price AND high_price = low_price AND low_price = close_price AND datetime LIKE '%15:31:%')
                ORDER BY datetime DESC
                LIMIT 1
            ''', (symbol,))
            
            filtered = cursor.fetchone()
            if filtered:
                print(f"  过滤后: {filtered[0]} | V={filtered[5]}")
        else:
            print(f"  → 正常K线，不过滤")
    print()

conn.close()
