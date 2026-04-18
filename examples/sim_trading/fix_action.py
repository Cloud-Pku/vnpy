"""修复数据库中的action字段"""
import sqlite3
from pathlib import Path

DB_PATH = Path('C:/Users/Lenovo/.vntrader/database.db')
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# 修复逻辑：根据direction和offset重新计算action
# direction=Long, offset=Open -> BUY
# direction=Long, offset=Close/Close Today -> COVER
# direction=Short, offset=Open -> SHORT
# direction=Short, offset=Close/Close Today -> SELL

print('=== 修复前 ===')
cursor.execute('''
    SELECT action, direction, offset, COUNT(*) 
    FROM trade_records 
    GROUP BY action, direction, offset
''')
for row in cursor.fetchall():
    print(f'action={row[0]}, direction={row[1]}, offset={row[2]}: {row[3]}条')

# 修复
cursor.execute('''
    UPDATE trade_records 
    SET action = CASE 
        WHEN direction = 'Long' AND offset LIKE 'Open%' THEN 'BUY'
        WHEN direction = 'Long' AND offset LIKE 'Close%' THEN 'COVER'
        WHEN direction = 'Short' AND offset LIKE 'Open%' THEN 'SHORT'
        WHEN direction = 'Short' AND offset LIKE 'Close%' THEN 'SELL'
        ELSE action
    END
''')

conn.commit()

print('\n=== 修复后 ===')
cursor.execute('''
    SELECT action, direction, offset, COUNT(*) 
    FROM trade_records 
    GROUP BY action, direction, offset
''')
for row in cursor.fetchall():
    print(f'action={row[0]}, direction={row[1]}, offset={row[2]}: {row[3]}条')

conn.close()
