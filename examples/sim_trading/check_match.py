"""检查K线和交易信号匹配情况"""
import urllib.request
import json

# 获取API数据
with urllib.request.urlopen('http://localhost:5002/api/data') as response:
    data = json.loads(response.read().decode())

output = []
output.append('=== 各品种数据统计 ===')

for symbol in ['rb2605.SHFE', 'i2605.DCE', 'MA605.CZCE', 'SA605.CZCE', 'p2605.DCE']:
    symbol_data = data.get('symbols', {}).get(symbol, {})
    bars = symbol_data.get('bars', [])
    trades = symbol_data.get('trades', [])
    
    output.append(f'\n{symbol}:')
    
    if bars:
        bar_times = [b['time'] for b in bars]
        output.append(f'  K线数: {len(bars)}, 时间范围: {bar_times[0]} ~ {bar_times[-1]}')
    else:
        output.append(f'  K线数: 0 (无数据)')
    
    if trades:
        trade_times = [t['time'] for t in trades]
        output.append(f'  交易信号数: {len(trades)}, 时间范围: {trade_times[0]} ~ {trade_times[-1]}')
        
        # 检查匹配情况
        if bars:
            bar_time_set = set(bar_times)
            matched = sum(1 for t in trade_times if t in bar_time_set)
            output.append(f'  匹配的mark数: {matched}/{len(trades)}')
            
            # 显示未匹配的交易信号
            unmatched = [t for t in trades if t['time'] not in bar_time_set]
            if unmatched:
                output.append(f'  未匹配的交易信号示例:')
                for t in unmatched[:3]:
                    output.append(f'    {t["time"]} {t["action"]} @ {t["price"]}')
    else:
        output.append(f'  交易信号数: 0')

# 写入结果
with open('d:/trading/vnpy/examples/sim_trading/match_check.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print('Done - 结果已写入 match_check.txt')
