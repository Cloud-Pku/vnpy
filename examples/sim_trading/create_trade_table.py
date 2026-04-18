"""
创建交易记录表，用于存储每笔成交详情
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("C:/Users/Lenovo/.vntrader/database.db")

def create_trade_table():
    """创建交易记录表"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # 创建交易记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            action TEXT NOT NULL,  -- BUY, SELL, SHORT, COVER
            direction TEXT NOT NULL,  -- LONG, SHORT
            offset TEXT NOT NULL,  -- OPEN, CLOSE
            price REAL NOT NULL,
            volume INTEGER NOT NULL,
            pos_after INTEGER NOT NULL,
            trade_datetime TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建索引
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trade_date ON trade_records(trade_date)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trade_symbol ON trade_records(symbol)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trade_strategy ON trade_records(strategy_name)
    ''')
    
    conn.commit()
    conn.close()
    print("✅ 交易记录表创建成功")

def check_table_structure():
    """查看表结构"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # 查看所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("\n📋 数据库表列表:")
    for table in tables:
        print(f"  - {table[0]}")
    
    # 查看dbbardata表结构
    if ('dbbardata',) in tables:
        cursor.execute('PRAGMA table_info(dbbardata)')
        print("\n📊 dbbardata表结构:")
        for row in cursor.fetchall():
            print(f"  {row[1]} ({row[2]})")
    
    # 查看trade_records表结构
    if ('trade_records',) in tables:
        cursor.execute('PRAGMA table_info(trade_records)')
        print("\n📊 trade_records表结构:")
        for row in cursor.fetchall():
            print(f"  {row[1]} ({row[2]})")
    
    conn.close()

if __name__ == "__main__":
    create_trade_table()
    check_table_structure()
