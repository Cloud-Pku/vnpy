"""检查交易记录详情，排查持仓计算问题"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print("=== 各品种完整交易记录及持仓计算 ===\n")

for symbol in ['rb2605', 'i2605', 'MA605', 'SA605', 'p2605']:
    print(f"\n{'='*60}")
    print(f"【{symbol}】")
    print('='*60)
    
    # 查询所有交易记录
    cursor.execute('''
        SELECT action, price, volume, pos_after, trade_datetime, id
        FROM trade_records 
        WHERE symbol = ? AND trade_date = '20260417'
        ORDER BY id
    ''', (symbol,))
    
    rows = cursor.fetchall()
    if not rows:
        print("  无交易记录")
        continue
    
    # 手动计算持仓
    calc_pos = 0
    print(f"\n{'时间':<20} {'操作':<10} {'价格':<8} {'量':<4} {'数据库持仓':<10} {'计算持仓':<10} {'一致'}")
    print('-' * 80)
    
    for row in rows:
        action, price, volume, db_pos, dt, tid = row
        
        # 计算持仓变化
        if action == 'BUY':
            calc_pos += volume
        elif action == 'SELL':
            calc_pos -= volume
        elif action == 'SHORT':
            calc_pos -= volume
        elif action == 'COVER':
            calc_pos += volume
        
        match = "✓" if calc_pos == db_pos else "✗"
        print(f"{dt:<20} {action:<10} {price:<8.1f} {volume:<4} {db_pos:<10} {calc_pos:<10} {match}")
    
    print(f"\n最终持仓: 数据库={rows[-1][3]}, 计算={calc_pos}")

conn.close()
