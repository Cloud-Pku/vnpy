"""
SimNow 仿真交易池策略
支持品种：上期所、大商所、郑商所、中金所
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional
from datetime import datetime


class ExchangeCode(Enum):
    """交易所代码"""
    SHFE = "SHFE"      # 上海期货交易所
    DCE = "DCE"        # 大连商品交易所
    CZCE = "CZCE"      # 郑州商品交易所
    CFFEX = "CFFEX"    # 中国金融期货交易所


@dataclass
class FutureContract:
    """期货合约信息"""
    symbol: str                    # 合约代码前缀
    exchange: ExchangeCode         # 交易所
    name: str                      # 品种名称
    category: str                  # 类别: 金属/能源/农产品/化工/股指/国债
    tick_size: float              # 最小变动价位
    contract_size: int            # 合约乘数
    margin_rate: float            # 保证金比例(估算)
    volatility_score: int         # 波动率评分 1-10
    liquidity_score: int          # 流动性评分 1-10
    trend_friendly: bool          # 是否适合趋势策略
    mean_reversion_friendly: bool # 是否适合均值回归策略


# ============================================================
# SimNow 支持的期货品种列表 (2024-2025)
# ============================================================

SIMNOW_CONTRACTS = [
    # ==================== 上期所 (SHFE) ====================
    # 贵金属
    FutureContract("au", ExchangeCode.SHFE, "黄金", "金属", 0.02, 1000, 0.10, 5, 9, True, False),
    FutureContract("ag", ExchangeCode.SHFE, "白银", "金属", 1, 15, 0.12, 8, 9, True, False),
    
    # 有色金属
    FutureContract("cu", ExchangeCode.SHFE, "铜", "金属", 10, 5, 0.10, 6, 9, True, False),
    FutureContract("al", ExchangeCode.SHFE, "铝", "金属", 5, 5, 0.10, 5, 8, True, False),
    FutureContract("zn", ExchangeCode.SHFE, "锌", "金属", 5, 5, 0.10, 6, 7, True, False),
    FutureContract("ni", ExchangeCode.SHFE, "镍", "金属", 10, 1, 0.12, 9, 7, True, False),
    FutureContract("sn", ExchangeCode.SHFE, "锡", "金属", 10, 1, 0.12, 8, 6, True, False),
    FutureContract("ss", ExchangeCode.SHFE, "不锈钢", "金属", 5, 5, 0.10, 6, 6, True, False),
    
    # 黑色金属
    FutureContract("rb", ExchangeCode.SHFE, "螺纹钢", "金属", 1, 10, 0.10, 6, 10, True, False),
    FutureContract("hc", ExchangeCode.SHFE, "热轧卷板", "金属", 1, 10, 0.10, 6, 8, True, False),
    FutureContract("wr", ExchangeCode.SHFE, "线材", "金属", 1, 10, 0.10, 5, 4, True, False),
    
    # 能源化工
    FutureContract("fu", ExchangeCode.SHFE, "燃料油", "能源", 1, 10, 0.10, 7, 7, True, False),
    FutureContract("bu", ExchangeCode.SHFE, "沥青", "能源", 1, 10, 0.10, 7, 7, True, False),
    FutureContract("ru", ExchangeCode.SHFE, "天然橡胶", "化工", 5, 10, 0.10, 7, 8, True, False),
    
    # ==================== 大商所 (DCE) ====================
    # 农产品
    FutureContract("a", ExchangeCode.DCE, "豆一", "农产品", 1, 10, 0.08, 5, 7, True, False),
    FutureContract("b", ExchangeCode.DCE, "豆二", "农产品", 1, 10, 0.08, 5, 6, True, False),
    FutureContract("m", ExchangeCode.DCE, "豆粕", "农产品", 1, 10, 0.08, 6, 9, True, False),
    FutureContract("y", ExchangeCode.DCE, "豆油", "农产品", 2, 10, 0.08, 6, 8, True, False),
    FutureContract("p", ExchangeCode.DCE, "棕榈油", "农产品", 2, 10, 0.08, 8, 8, True, False),
    FutureContract("c", ExchangeCode.DCE, "玉米", "农产品", 1, 10, 0.08, 4, 7, False, True),
    FutureContract("cs", ExchangeCode.DCE, "玉米淀粉", "农产品", 1, 10, 0.08, 4, 5, False, True),
    
    # 化工
    FutureContract("l", ExchangeCode.DCE, "聚乙烯", "化工", 1, 5, 0.08, 5, 7, True, False),
    FutureContract("v", ExchangeCode.DCE, "聚氯乙烯", "化工", 1, 5, 0.08, 5, 7, True, False),
    FutureContract("pp", ExchangeCode.DCE, "聚丙烯", "化工", 1, 5, 0.08, 5, 7, True, False),
    FutureContract("eg", ExchangeCode.DCE, "乙二醇", "化工", 1, 10, 0.08, 6, 7, True, False),
    FutureContract("eb", ExchangeCode.DCE, "苯乙烯", "化工", 1, 5, 0.08, 8, 7, True, False),
    FutureContract("pg", ExchangeCode.DCE, "液化石油气", "能源", 1, 20, 0.08, 7, 6, True, False),
    
    # 黑色系
    FutureContract("i", ExchangeCode.DCE, "铁矿石", "金属", 0.5, 100, 0.11, 8, 10, True, False),
    FutureContract("j", ExchangeCode.DCE, "焦炭", "能源", 0.5, 100, 0.11, 8, 8, True, False),
    FutureContract("jm", ExchangeCode.DCE, "焦煤", "能源", 0.5, 60, 0.11, 8, 7, True, False),
    
    # ==================== 郑商所 (CZCE) ====================
    # 农产品
    FutureContract("CF", ExchangeCode.CZCE, "棉花", "农产品", 5, 5, 0.09, 6, 8, True, False),
    FutureContract("SR", ExchangeCode.CZCE, "白糖", "农产品", 1, 10, 0.09, 6, 8, True, False),
    FutureContract("TA", ExchangeCode.CZCE, "PTA", "化工", 2, 5, 0.09, 6, 9, True, False),
    FutureContract("MA", ExchangeCode.CZCE, "甲醇", "化工", 1, 10, 0.09, 7, 8, True, False),
    FutureContract("RM", ExchangeCode.CZCE, "菜粕", "农产品", 1, 10, 0.09, 6, 7, True, False),
    FutureContract("OI", ExchangeCode.CZCE, "菜油", "农产品", 1, 10, 0.09, 6, 6, True, False),
    FutureContract("AP", ExchangeCode.CZCE, "苹果", "农产品", 1, 10, 0.10, 9, 6, True, False),
    FutureContract("CJ", ExchangeCode.CZCE, "红枣", "农产品", 5, 5, 0.12, 8, 4, True, False),
    
    # 化工/能源
    FutureContract("FG", ExchangeCode.CZCE, "玻璃", "化工", 1, 20, 0.09, 7, 7, True, False),
    FutureContract("SA", ExchangeCode.CZCE, "纯碱", "化工", 1, 20, 0.09, 9, 7, True, False),
    FutureContract("UR", ExchangeCode.CZCE, "尿素", "化工", 1, 20, 0.09, 7, 6, True, False),
    FutureContract("PF", ExchangeCode.CZCE, "短纤", "化工", 2, 5, 0.09, 6, 5, True, False),
    
    # ==================== 中金所 (CFFEX) ====================
    # 股指期货
    FutureContract("IF", ExchangeCode.CFFEX, "沪深300", "股指", 0.2, 300, 0.12, 6, 10, True, False),
    FutureContract("IC", ExchangeCode.CFFEX, "中证500", "股指", 0.2, 200, 0.12, 7, 9, True, False),
    FutureContract("IM", ExchangeCode.CFFEX, "中证1000", "股指", 0.2, 200, 0.12, 8, 8, True, False),
    FutureContract("IH", ExchangeCode.CFFEX, "上证50", "股指", 0.2, 300, 0.12, 5, 9, True, False),
    
    # 国债期货
    FutureContract("T", ExchangeCode.CFFEX, "10年期国债", "国债", 0.005, 10000, 0.02, 3, 8, True, False),
    FutureContract("TF", ExchangeCode.CFFEX, "5年期国债", "国债", 0.005, 10000, 0.02, 3, 7, True, False),
    FutureContract("TS", ExchangeCode.CFFEX, "2年期国债", "国债", 0.005, 10000, 0.02, 2, 6, False, True),
]


def get_contract_symbol(contract: FutureContract, year_month: str) -> str:
    """
    生成完整合约代码
    
    Args:
        contract: 合约基础信息
        year_month: 年月代码，如 "2610" 表示 2026年10月
    
    Returns:
        完整合约代码，如 "rb2610.SHFE"
    """
    return f"{contract.symbol}{year_month}.{contract.exchange.value}"


def select_trading_pool(
    strategy_type: str = "trend",           # 策略类型: trend/mean_reversion/multi_factor
    risk_level: str = "medium",             # 风险等级: low/medium/high
    max_contracts: int = 5,                 # 最大合约数
    preferred_categories: Optional[List[str]] = None,  # 偏好类别
    exclude_symbols: Optional[List[str]] = None        # 排除的品种
) -> List[Dict]:
    """
    选股策略：根据策略类型和风险偏好选择交易池
    
    Args:
        strategy_type: 策略类型
            - "trend": 趋势跟踪策略，选择趋势性强、波动率适中的品种
            - "mean_reversion": 均值回归策略，选择震荡性强、均值回复明显的品种
            - "multi_factor": 多因子策略，选择流动性好、信息效率高的品种
        
        risk_level: 风险等级
            - "low": 低波动、高流动性，适合稳健型策略
            - "medium": 平衡配置，适合一般策略
            - "high": 高波动、高弹性，适合激进策略
    
    Returns:
        选中的合约配置列表
    """
    candidates = SIMNOW_CONTRACTS.copy()
    
    # 排除指定品种
    if exclude_symbols:
        candidates = [c for c in candidates if c.symbol not in exclude_symbols]
    
    # 根据策略类型筛选
    if strategy_type == "trend":
        candidates = [c for c in candidates if c.trend_friendly]
        # 趋势策略偏好：波动率适中偏高，流动性好
        candidates.sort(key=lambda x: (x.volatility_score * 0.6 + x.liquidity_score * 0.4), reverse=True)
    
    elif strategy_type == "mean_reversion":
        candidates = [c for c in candidates if c.mean_reversion_friendly]
        # 均值回归策略偏好：波动率适中，趋势性弱
        candidates.sort(key=lambda x: (x.liquidity_score * 0.7 + (10 - x.volatility_score) * 0.3), reverse=True)
    
    elif strategy_type == "multi_factor":
        # 多因子策略偏好：流动性最好，覆盖多个板块
        candidates.sort(key=lambda x: x.liquidity_score, reverse=True)
    
    # 根据风险等级过滤
    if risk_level == "low":
        candidates = [c for c in candidates if c.volatility_score <= 5]
    elif risk_level == "medium":
        candidates = [c for c in candidates if 4 <= c.volatility_score <= 7]
    elif risk_level == "high":
        candidates = [c for c in candidates if c.volatility_score >= 6]
    
    # 类别偏好过滤
    if preferred_categories:
        candidates = [c for c in candidates if c.category in preferred_categories]
    
    # 选择前N个
    selected = candidates[:max_contracts]
    
    # 生成配置
    current_year = datetime.now().year % 100  # 获取年份后两位
    current_month = datetime.now().month
    
    # 生成主力合约月份（简单逻辑：选择当前月或下个月的合约）
    def get_main_contract_month(symbol: str) -> str:
        """简单的主力合约月份选择逻辑"""
        # 实际应用中应该根据交割月份规则来确定
        months = ["01", "05", "09"]  # 常见的主力合约月份
        for m in months:
            month_num = int(m)
            if month_num >= current_month:
                return f"{current_year:02d}{m}"
        return f"{current_year + 1:02d}{months[0]}"
    
    result = []
    for contract in selected:
        year_month = get_main_contract_month(contract.symbol)
        vt_symbol = get_contract_symbol(contract, year_month)
        result.append({
            "vt_symbol": vt_symbol,
            "name": contract.name,
            "category": contract.category,
            "exchange": contract.exchange.value,
            "volatility": contract.volatility_score,
            "liquidity": contract.liquidity_score,
            "margin_rate": contract.margin_rate,
        })
    
    return result


def print_pool_suggestions():
    """打印不同策略类型的交易池建议"""
    print("=" * 80)
    print("SimNow 仿真交易池策略建议")
    print("=" * 80)
    
    # 趋势策略交易池
    print("\n【趋势跟踪策略 - 中等风险】")
    print("-" * 80)
    trend_pool = select_trading_pool(
        strategy_type="trend",
        risk_level="medium",
        max_contracts=5
    )
    for i, item in enumerate(trend_pool, 1):
        print(f"{i}. {item['vt_symbol']:15} | {item['name']:8} | {item['category']:6} | "
              f"波动:{item['volatility']}/10 | 流动性:{item['liquidity']}/10")
    
    # 多因子策略交易池
    print("\n【多因子策略 - 低风险管理】")
    print("-" * 80)
    multi_pool = select_trading_pool(
        strategy_type="multi_factor",
        risk_level="low",
        max_contracts=5
    )
    for i, item in enumerate(multi_pool, 1):
        print(f"{i}. {item['vt_symbol']:15} | {item['name']:8} | {item['category']:6} | "
              f"波动:{item['volatility']}/10 | 流动性:{item['liquidity']}/10")
    
    # 激进型交易池
    print("\n【激进型策略 - 高风险高波动】")
    print("-" * 80)
    aggressive_pool = select_trading_pool(
        strategy_type="trend",
        risk_level="high",
        max_contracts=5
    )
    for i, item in enumerate(aggressive_pool, 1):
        print(f"{i}. {item['vt_symbol']:15} | {item['name']:8} | {item['category']:6} | "
              f"波动:{item['volatility']}/10 | 流动性:{item['liquidity']}/10")
    
    print("\n" + "=" * 80)
    print("说明：")
    print("- 合约代码中的数字为示例主力合约月份，实际交易时请根据当前主力合约调整")
    print("- 波动率评分：1-10，越高表示价格波动越大")
    print("- 流动性评分：1-10，越高表示成交量越大、滑点越小")
    print("- 建议先用 --check-connection 模式验证合约代码是否正确")
    print("=" * 80)


if __name__ == "__main__":
    print_pool_suggestions()
