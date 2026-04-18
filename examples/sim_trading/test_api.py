"""测试API返回的交易记录"""
import urllib.request
import json

with urllib.request.urlopen("http://localhost:5002/api/data") as resp:
    data = json.loads(resp.read().decode())

print("=== 交易记录 ===")
for symbol, info in data.get('symbols', {}).items():
    trades = info.get('trades', [])
    if trades:
        print(f"\n{symbol}:")
        for t in trades[:5]:
            print(f"  {t['time']} | {t['action']} | 价格={t['price']} | 持仓={t['pos_after']}")
