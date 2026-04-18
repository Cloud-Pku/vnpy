"""检查各期货品种的成交量统计"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

print(f"=== 各品种成交量统计 ({datetime.now().strftime('%Y-%m-%d')}) ===\n")

today = datetime.now().strftime("%Y-%m-%d")

for symbol in ['rb2605', 'i2605', 'MA605', 'SA605', 'p2605']:
    # 查询今日成交量统计
    cursor.execute('''
        SELECT 
            COUNT(*) as bar_count,
            SUM(volume) as total_volume,
            AVG(volume) as avg_volume,
            MAX(volume) as max_volume,
            MIN(volume) as min_volume,
            MAX(datetime) as last_update
        FROM dbbardata 
        WHERE symbol = ? AND datetime >= ?
    ''', (symbol, today))
    
    row = cursor.fetchone()
    
    print(f"【{symbol}】")
    print(f"  K线数量: {row[0]} 条")
    print(f"  总成交量: {row[1]:.0f} 手" if row[1] else "  总成交量: 0 手")
    print(f"  平均成交量: {row[2]:.1f} 手/分钟" if row[2] else "  平均成交量: 0 手/分钟")
    print(f"  最大成交量: {row[3]:.0f} 手" if row[3] else "  最大成交量: 0 手")
    print(f"  最小成交量: {row[4]:.0f} 手" if row[4] else "  最小成交量: 0 手")
    print(f"  最后更新: {row[5]}")
    print()

# 对比各品种成交量差异
print("=== 成交量对比 ===")
cursor.execute('''
    SELECT 
        symbol,
        SUM(volume) as total_volume
    FROM dbbardata 
    WHERE datetime >= ? AND symbol IN ('rb2605', 'i2605', 'MA605', 'SA605', 'p2605')
    GROUP BY symbol
    ORDER BY total_volume DESC
''', (today,))

volumes = cursor.fetchall()
if volumes:
    max_vol = max(v[1] for v in volumes)
    print(f"{'品种':<10} {'总成交量':>12} {'占比':>8}")
    print("-" * 35)
    for sym, vol in volumes:
        pct = (vol / max_vol * 100) if max_vol > 0 else 0
        print(f"{sym:<10} {vol:>12.0f} {pct:>7.1f}%")

conn.close()
