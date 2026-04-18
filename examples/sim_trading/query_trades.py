"""
查询交易记录
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("C:/Users/Lenovo/.vntrader/database.db")


def query_trades(date_str=None, strategy_name=None, symbol=None):
    """查询交易记录"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    # 构建查询条件
    conditions = ["trade_date = ?"]
    params = [date_str]
    
    if strategy_name:
        conditions.append("strategy_name = ?")
        params.append(strategy_name)
    
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)
    
    where_clause = " AND ".join(conditions)
    
    # 查询交易记录
    cursor.execute(f'''
        SELECT strategy_name, symbol, action, direction, offset, 
               price, volume, pos_after, trade_datetime
        FROM trade_records
        WHERE {where_clause}
        ORDER BY trade_datetime
    ''', params)
    
    rows = cursor.fetchall()
    
    if not rows:
        print(f"📭 没有找到 {date_str} 的交易记录")
        conn.close()
        return
    
    print(f"\n📊 {date_str} 交易记录 ({len(rows)} 笔):")
    print("=" * 100)
    print(f"{'策略':<12} {'品种':<10} {'动作':<8} {'方向':<6} {'开平':<6} {'价格':<10} {'数量':<6} {'持仓':<6} {'时间'}")
    print("-" * 100)
    
    for row in rows:
        strategy, sym, action, direction, offset, price, volume, pos_after, dt = row
        print(f"{strategy:<12} {sym:<10} {action:<8} {direction:<6} {offset:<6} {price:<10.2f} {volume:<6} {pos_after:<6} {dt}")
    
    # 统计盈亏（简化计算）
    print("\n📈 盈亏统计:")
    print("-" * 50)
    
    # 按品种统计
    cursor.execute(f'''
        SELECT symbol, 
               SUM(CASE WHEN action IN ('BUY', 'COVER') THEN price * volume ELSE 0 END) as buy_amount,
               SUM(CASE WHEN action IN ('SELL', 'SHORT') THEN price * volume ELSE 0 END) as sell_amount,
               SUM(CASE WHEN action IN ('BUY', 'COVER') THEN volume ELSE 0 END) as buy_volume,
               SUM(CASE WHEN action IN ('SELL', 'SHORT') THEN volume ELSE 0 END) as sell_volume
        FROM trade_records
        WHERE {where_clause}
        GROUP BY symbol
    ''', params)
    
    for row in cursor.fetchall():
        symbol, buy_amount, sell_amount, buy_vol, sell_vol = row
        realized_pnl = sell_amount - buy_amount if sell_vol > 0 and buy_vol > 0 else 0
        print(f"  {symbol}: 买入={buy_vol}手, 卖出={sell_vol}手, 实现盈亏={realized_pnl:.2f}")
    
    conn.close()


def export_trades_to_csv(date_str=None, output_file=None):
    """导出交易记录到CSV"""
    import csv
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    if output_file is None:
        output_file = f"trades_{date_str}.csv"
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM trade_records
        WHERE trade_date = ?
        ORDER BY trade_datetime
    ''', (date_str,))
    
    rows = cursor.fetchall()
    
    if not rows:
        print(f"📭 没有找到 {date_str} 的交易记录")
        conn.close()
        return
    
    # 获取列名
    cursor.execute('PRAGMA table_info(trade_records)')
    columns = [row[1] for row in cursor.fetchall()]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    
    print(f"✅ 已导出 {len(rows)} 笔交易记录到 {output_file}")
    conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "export":
            date = sys.argv[2] if len(sys.argv) > 2 else None
            export_trades_to_csv(date)
        else:
            query_trades(sys.argv[1])
    else:
        # 查询今天的交易
        query_trades()
