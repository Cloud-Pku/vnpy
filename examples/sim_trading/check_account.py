"""检查账户状态"""
import requests
import json

resp = requests.get('http://localhost:5002/api/account')
data = resp.json()
print('=== 账户状态 ===')
print(f'余额: {data["balance"]:,.1f}')
print(f'可用: {data["available"]:,.1f}')
print(f'冻结: {data["frozen"]:,.1f}')
print(f'盈亏: {data["pnl"]:,.1f}')
print()
print('=== 持仓详情 ===')
for pos in data['positions']:
    if pos['pos'] != 0:
        print(f'{pos["symbol"]}: 持仓={pos["pos"]}, 成本={pos["cost"]}, 当前价={pos["price"]}, 盈亏={pos["pnl"]:.1f}')

# 计算总盈亏明细
print()
print('=== 盈亏分析 ===')
total_pnl = 0
for pos in data['positions']:
    if pos['pos'] != 0:
        total_pnl += pos['pnl']
        print(f'{pos["symbol"]}: {pos["pnl"]:.1f}')
print(f'合计: {total_pnl:.1f}')
