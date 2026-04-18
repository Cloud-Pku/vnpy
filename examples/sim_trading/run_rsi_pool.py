"""
RSI高频交易策略池 - 夜盘/日盘快速交易验证
- 使用短周期RSI指标，产生频繁交易信号
- 适合快速验证监控系统的买卖点标记功能
"""
import sys
import os

# 切换到脚本所在目录，确保策略加载正确
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)

from dataclasses import dataclass
from datetime import datetime
from time import sleep
from typing import List, Optional, Dict

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import MainEngine, LogEngine
from vnpy.trader.utility import load_json, save_json
from vnpy.trader.constant import Exchange
from vnpy.trader.object import TickData, BarData, SubscribeRequest
from vnpy_ctp import CtpGateway
from vnpy_ctastrategy import CtaStrategyApp, CtaEngine
from vnpy_ctastrategy.base import EVENT_CTA_LOG
from vnpy.trader.database import BaseDatabase, get_database
from vnpy.trader.datafeed import BaseDatafeed, get_datafeed

# 导入RSI策略 - 先从当前目录，再从用户目录
try:
    from strategies.rsi_strategy import RsiStrategy
except ImportError:
    import sys
    sys.path.insert(0, os.path.expanduser('~/.vntrader'))
    from strategies.rsi_strategy import RsiStrategy

# 导入BarGenerator用于K线记录
try:
    from vnpy.trader.utility import BarGenerator
except ImportError:
    from vnpy_ctastrategy.template import BarGenerator

# 配置日志
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================
# K线记录器（多品种版本）
# ============================================================
class MultiBarRecorder:
    """
    多品种K线记录器
    - 为每个品种维护独立的BarGenerator
    - 批量写入数据库，减少SQLite锁竞争
    """

    def __init__(self, database: BaseDatabase, flush_size: int = 5) -> None:
        self.database = database
        self.flush_size = flush_size
        self.last_flush_time = datetime.now()
        
        # 每个品种一个BarGenerator
        self.generators: Dict[str, BarGenerator] = {}
        self.buffers: Dict[str, List[BarData]] = {}
        self.bar_counts: Dict[str, int] = {}
        
    def register_symbol(self, vt_symbol: str) -> None:
        """注册需要记录的品种"""
        if vt_symbol not in self.generators:
            self.generators[vt_symbol] = BarGenerator(self._create_on_bar(vt_symbol))
            self.buffers[vt_symbol] = []
            self.bar_counts[vt_symbol] = 0
            logger.info(f"[落库] 已注册品种: {vt_symbol}")

    def _create_on_bar(self, vt_symbol: str):
        """为指定品种创建on_bar回调"""
        def on_bar(bar: BarData) -> None:
            self.bar_counts[vt_symbol] += 1
            self.buffers[vt_symbol].append(bar)
            
            # 打印日志
            exchange = getattr(bar.exchange, "value", bar.exchange)
            logger.info(
                f"[落库] {bar.symbol}.{exchange} | "
                f"{bar.datetime.strftime('%Y-%m-%d %H:%M')} | "
                f"O={bar.open_price:.1f} H={bar.high_price:.1f} "
                f"L={bar.low_price:.1f} C={bar.close_price:.1f} "
                f"V={bar.volume:.0f} | 累计 {self.bar_counts[vt_symbol]} 根"
            )
            
            # 检查是否需要批量写入
            if len(self.buffers[vt_symbol]) >= self.flush_size:
                self.flush()
        
        return on_bar

    def on_tick(self, tick: TickData) -> None:
        """处理Tick数据"""
        vt_symbol = tick.vt_symbol
        if vt_symbol in self.generators:
            try:
                self.generators[vt_symbol].update_tick(tick)
            except Exception:
                logger.exception(f"[{vt_symbol}] K线落库处理异常")

    def flush(self) -> None:
        """批量刷入数据库"""
        all_bars: List[BarData] = []
        
        for vt_symbol, buffer in self.buffers.items():
            if buffer:
                all_bars.extend(buffer)
                buffer.clear()
        
        if all_bars:
            try:
                self.database.save_bar_data(all_bars, stream=True)
                logger.info(f"[落库] 批量写入 {len(all_bars)} 根K线")
            except Exception as e:
                logger.error(f"[落库] 数据库写入失败: {e}")
        
        self.last_flush_time = datetime.now()

    def check_force_flush(self) -> None:
        """检查是否需要强制刷新（按时间间隔）"""
        elapsed = (datetime.now() - self.last_flush_time).total_seconds()
        if elapsed >= 30:  # 30秒强制刷新
            self.flush()

    def get_summary(self) -> Dict[str, int]:
        """获取记录统计"""
        return dict(self.bar_counts)


# ============================================================
# SimNow CTP 配置（与之前相同）
# ============================================================
CTP_SETTING = {
    "用户名": "258545",
    "密码": "!CzhCy1124",
    "经纪商代码": "9999",
    "交易服务器": os.getenv("SIMNOW_TD_ADDRESS", "182.254.243.31:30001"),
    "行情服务器": os.getenv("SIMNOW_MD_ADDRESS", "182.254.243.31:30011"),
    "产品名称": "simnow_client_test",
    "授权编码": "0000000000000000",
    "柜台环境": os.getenv("SIMNOW_ENVIRONMENT", "实盘"),
}


@dataclass
class StrategyConfig:
    """策略配置"""
    class_name: str
    strategy_name: str
    vt_symbol: str
    setting: dict


# ============================================================
# RSI策略池配置 - 短周期高频交易
# ============================================================
TRADING_POOL: List[StrategyConfig] = [
    # 螺纹钢 - RSI短周期
    StrategyConfig(
        class_name="RsiStrategy",
        strategy_name="RSI高频_螺纹",
        vt_symbol="rb2605.SHFE",
        setting={
            "rsi_window": 5,           # 超短周期
            "rsi_overbought": 60,      # 较低超买线
            "rsi_oversold": 40,        # 较高超卖线
        }
    ),
    # 铁矿石 - RSI短周期
    StrategyConfig(
        class_name="RsiStrategy",
        strategy_name="RSI高频_铁矿",
        vt_symbol="i2605.DCE",
        setting={
            "rsi_window": 5,
            "rsi_overbought": 60,
            "rsi_oversold": 40,
        }
    ),
    # 甲醇 - RSI短周期
    StrategyConfig(
        class_name="RsiStrategy",
        strategy_name="RSI高频_甲醇",
        vt_symbol="MA605.CZCE",
        setting={
            "rsi_window": 5,
            "rsi_overbought": 60,
            "rsi_oversold": 40,
        }
    ),
    # 纯碱 - RSI短周期
    StrategyConfig(
        class_name="RsiStrategy",
        strategy_name="RSI高频_纯碱",
        vt_symbol="SA605.CZCE",
        setting={
            "rsi_window": 5,
            "rsi_overbought": 60,
            "rsi_oversold": 40,
        }
    ),
    # 棕榈油 - RSI短周期
    StrategyConfig(
        class_name="RsiStrategy",
        strategy_name="RSI高频_棕榈",
        vt_symbol="p2605.DCE",
        setting={
            "rsi_window": 5,
            "rsi_overbought": 60,
            "rsi_oversold": 40,
        }
    ),
]


def validate_config() -> bool:
    """校验配置"""
    if not CTP_SETTING["用户名"] or not CTP_SETTING["密码"]:
        logger.error("请填写SimNow账号信息！")
        return False
    return True


def run_rsi_pool(
    check_connection: bool = False,
    wait_seconds: int = 25,
) -> None:
    """启动RSI高频交易池"""
    
    if not validate_config():
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("🚀 RSI高频交易池启动")
    logger.info("=" * 60)
    logger.info(f"交易品种数: {len(TRADING_POOL)}")
    for cfg in TRADING_POOL:
        logger.info(f"  - {cfg.vt_symbol}: {cfg.strategy_name} (RSI周期={cfg.setting['rsi_window']})")
    logger.info("=" * 60)
    
    # 1. 创建引擎
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    logger.info("主引擎创建成功")
    
    # 2. 添加CTP网关
    main_engine.add_gateway(CtpGateway)
    logger.info("CTP网关添加成功")
    
    # 3. 添加CTA策略引擎
    cta_engine: CtaEngine = main_engine.add_app(CtaStrategyApp)
    logger.info("CTA策略引擎添加成功")
    
    # 4. 注册日志事件
    log_engine: LogEngine = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    logger.info("日志事件监听注册完成")
    
    # 5. 连接SimNow
    main_engine.connect(CTP_SETTING, "CTP")
    logger.info("正在连接SimNow CTP仿真服务器...")
    logger.info(f"等待连接建立和合约数据下载（约 {wait_seconds} 秒）...")
    sleep(wait_seconds)
    
    # 6. 初始化K线记录器
    database: BaseDatabase = get_database()
    bar_recorder = MultiBarRecorder(database)
    for cfg in TRADING_POOL:
        bar_recorder.register_symbol(cfg.vt_symbol)
    logger.info("K线记录器初始化完成")
    
    # 7. 订阅行情
    for cfg in TRADING_POOL:
        contract = main_engine.get_contract(cfg.vt_symbol)
        if contract:
            req = SubscribeRequest(symbol=contract.symbol, exchange=contract.exchange)
            main_engine.subscribe(req, "CTP")
            logger.info(f"已订阅行情: {cfg.vt_symbol}")
        else:
            logger.warning(f"未找到合约: {cfg.vt_symbol}")
    
    # 8. 初始化CTA引擎
    cta_engine.init_engine()
    logger.info("CTA策略引擎初始化完成")
    
    # 8.5 手动注册RSI策略类（确保策略可用）
    cta_engine.classes["RsiStrategy"] = RsiStrategy
    logger.info(f"✅ 已注册策略类: RsiStrategy")
    
    # 9. 添加策略实例
    for cfg in TRADING_POOL:
        cta_engine.add_strategy(
            class_name=cfg.class_name,
            strategy_name=cfg.strategy_name,
            vt_symbol=cfg.vt_symbol,
            setting=cfg.setting,
        )
        logger.info(f"策略 [{cfg.strategy_name}] 添加成功")
    
    # 10. 初始化策略
    for cfg in TRADING_POOL:
        cta_engine.init_strategy(cfg.strategy_name)
    
    logger.info("等待策略初始化完成...")
    sleep(15)
    
    # 10.5 同步持仓状态（关键！确保策略持仓与实际账户一致）
    logger.info("=" * 60)
    logger.info("📊 同步持仓状态...")
    for cfg in TRADING_POOL:
        strategy = cta_engine.strategies.get(cfg.strategy_name)
        if strategy:
            # 从MainEngine的positions字典中查找对应持仓
            # vt_positionid 格式: symbol.exchange.direction
            parts = cfg.vt_symbol.split('.')
            if len(parts) == 2:
                sym, exch = parts
                # 查找多仓和空仓
                long_posid = f"{sym}.{exch}.Long"
                short_posid = f"{sym}.{exch}.Short"
                
                long_pos_data = main_engine.get_position(long_posid)
                short_pos_data = main_engine.get_position(short_posid)
                
                long_vol = long_pos_data.volume if long_pos_data else 0
                short_vol = short_pos_data.volume if short_pos_data else 0
                actual_pos = long_vol - short_vol
                
                logger.info(
                    f"  {cfg.vt_symbol}: 策略持仓={strategy.pos}, "
                    f"实际持仓={actual_pos} (多={long_vol}, 空={short_vol})"
                )
                # 如果不一致，需要警告
                if strategy.pos != actual_pos:
                    logger.warning(
                        f"  ⚠️ 持仓不一致！策略={strategy.pos}, 实际={actual_pos}"
                    )
            else:
                logger.info(f"  {cfg.vt_symbol}: 策略持仓={strategy.pos}")
    logger.info("=" * 60)
    
    # 11. 启动策略
    for cfg in TRADING_POOL:
        cta_engine.start_strategy(cfg.strategy_name)
        logger.info(f"策略 [{cfg.strategy_name}] 已启动！")
    
    logger.info("=" * 60)
    logger.info("🎯 RSI高频交易池运行中！")
    logger.info("特点：短周期RSI，频繁交易信号")
    logger.info("按 Ctrl+C 停止...")
    logger.info("=" * 60)
    
    # 12. 主循环
    try:
        while True:
            sleep(1)
            
            # 处理Tick数据并记录K线
            for cfg in TRADING_POOL:
                strategy = cta_engine.strategies.get(cfg.strategy_name)
                if strategy and hasattr(strategy, 'last_tick') and strategy.last_tick:
                    bar_recorder.on_tick(strategy.last_tick)
            
            # 强制刷新K线（每30秒）
            bar_recorder.check_force_flush()
            
            # 每10秒打印一次状态
            if int(datetime.now().timestamp()) % 10 == 0:
                for cfg in TRADING_POOL:
                    strategy = cta_engine.strategies.get(cfg.strategy_name)
                    if strategy and hasattr(strategy, 'rsi_value'):
                        logger.info(
                            f"[状态] {cfg.strategy_name} | "
                            f"RSI={strategy.rsi_value:.1f} | 持仓={strategy.pos}"
                        )
    
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
    
    # 13. 清理退出
    main_engine.close()
    logger.info("RSI高频交易池已安全关闭")


if __name__ == "__main__":
    run_rsi_pool()
