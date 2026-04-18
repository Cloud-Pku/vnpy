"""查询SimNow上所有可用的期货合约"""
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import Exchange
from vnpy.trader.setting import SETTINGS
from vnpy.trader.logger import INFO
from vnpy_ctp import CtpGateway
import os
from time import sleep

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = False

CTP_SETTING = {
    "用户名": os.getenv("SIMNOW_USER", "258545"),
    "密码": os.getenv("SIMNOW_PASSWORD", "!CzhCy1124"),
    "经纪商代码": "9999",
    "交易服务器": "182.254.243.31:30001",
    "行情服务器": "182.254.243.31:30011",
    "产品名称": "simnow_client_test",
    "授权编码": "0000000000000000",
    "柜台环境": "实盘",
}

def main():
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(CtpGateway)
    main_engine.connect(CTP_SETTING, "CTP")
    
    print("正在连接SimNow...")
    sleep(30)
    
    contracts = main_engine.get_all_contracts()
    print(f"\n共获取 {len(contracts)} 个合约\n")
    
    # 按交易所分组
    by_exchange = {}
    for c in contracts:
        ex = c.exchange.value
        if ex not in by_exchange:
            by_exchange[ex] = []
        by_exchange[ex].append(c)
    
    output_lines = []
    output_lines.append("=" * 70)
    output_lines.append("SimNow 可用期货合约列表")
    output_lines.append("=" * 70)
    
    # 打印各交易所的主力合约（按成交量排序）
    for exchange in ["SHFE", "DCE", "CZCE", "CFFEX"]:
        if exchange not in by_exchange:
            continue
        
        output_lines.append(f"\n交易所: {exchange}")
        output_lines.append("-" * 70)
        
        # 按品种分组
        by_symbol = {}
        for c in by_exchange[exchange]:
            # 提取品种代码（去掉数字）
            symbol_prefix = ''.join(filter(str.isalpha, c.symbol))
            if symbol_prefix not in by_symbol:
                by_symbol[symbol_prefix] = []
            by_symbol[symbol_prefix].append(c)
        
        # 打印每个品种的主力合约
        for symbol_prefix in sorted(by_symbol.keys()):
            contract_list = by_symbol[symbol_prefix]
            # 取第一个作为代表
            c = contract_list[0]
            name = getattr(c, 'name', c.symbol)
            # 显示前3个合约
            vt_symbols = [c.vt_symbol for c in sorted(contract_list, key=lambda x: x.vt_symbol)[:3]]
            line = f"  {symbol_prefix:6} | {name:12} | {', '.join(vt_symbols)}"
            output_lines.append(line)
    
    output_lines.append("\n" + "=" * 70)
    output_lines.append("查询完成")
    
    # 输出到控制台和文件
    result = "\n".join(output_lines)
    print(result)
    
    with open("available_contracts.txt", "w", encoding="utf-8") as f:
        f.write(result)
    
    print(f"\n已保存到 available_contracts.txt")
    
    main_engine.close()

if __name__ == "__main__":
    main()
