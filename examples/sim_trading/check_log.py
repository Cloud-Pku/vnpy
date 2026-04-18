"""检查日志中的成交记录"""
from pathlib import Path

log_file = Path('C:/Users/Lenovo/.vntrader/log/vt_20260417.log')
if log_file.exists():
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # 查找所有成交记录
    trades = []
    for line in lines:
        if '[成交]' in line:
            trades.append(line.strip())
    
    print(f'找到 {len(trades)} 条成交记录')
    print('\n前10条:')
    for t in trades[:10]:
        print(t)
else:
    print('日志文件不存在')
