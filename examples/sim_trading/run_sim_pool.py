"""
SimNow 仿真交易启动脚本 - 多品种交易池版本
- 连接 SimNow CTP 仿真服务器
- 支持多品种同时交易（共享CTP连接）
- 纯命令行运行，无需 GUI

数据库并发处理：
- 使用单进程多策略架构，避免SQLite并发冲突
- 批量写入K线数据，减少IO操作
- 每个品种独立的BarGenerator，统一flush到数据库
"""
import argparse
import os
import sys
from time import sleep
from datetime import datetime, time
from typing import Dict, List, Optional
from dataclasses import dataclass

from vnpy.event import Event, EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine, LogEngine
from vnpy.trader.object import BarData, TickData
from vnpy.trader.event import EVENT_TICK
from vnpy.trader.database import BaseDatabase, get_database
from vnpy.trader.logger import INFO, logger
from vnpy.trader.utility import BarGenerator

from vnpy_ctp import CtpGateway
from vnpy_ctastrategy import CtaStrategyApp, CtaEngine
from vnpy_ctastrategy.base import EVENT_CTA_LOG


# ============================================================
# 全局配置
# ============================================================
SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True

# ============================================================
# SimNow CTP 连接配置
# ============================================================
CTP_SETTING = {
    "用户名": os.getenv("SIMNOW_USER", "258545"),
    "密码": os.getenv("SIMNOW_PASSWORD", "!CzhCy1124"),
    "经纪商代码": "9999",
    "交易服务器": os.getenv("SIMNOW_TD_ADDRESS", "182.254.243.31:30001"),
    "行情服务器": os.getenv("SIMNOW_MD_ADDRESS", "182.254.243.31:30011"),
    "产品名称": "simnow_client_test",
    "授权编码": "0000000000000000",
    "柜台环境": os.getenv("SIMNOW_ENVIRONMENT", "实盘"),
}

# ============================================================
# 交易池配置
# ============================================================
@dataclass
class StrategyConfig:
    """策略配置数据类"""
    class_name: str
    strategy_name: str
    vt_symbol: str
    setting: dict


# 多品种交易池配置
# 注意：请根据实际主力合约调整合约月份
# 上期所/大商所格式：小写字母+4位数字，如 rb2605, i2605
# 郑商所格式：大写字母+3位数字，如 MA605, SA605
TRADING_POOL: List[StrategyConfig] = [
    # ==================== 趋势策略组合 - 高流动性品种 ====================
    # 黑色系
    StrategyConfig(
        class_name="DoubleMaStrategy",
        strategy_name="双均线_螺纹",
        vt_symbol="rb2605.SHFE",
        setting={"fast_window": 10, "slow_window": 20}
    ),
    StrategyConfig(
        class_name="DoubleMaStrategy",
        strategy_name="双均线_铁矿",
        vt_symbol="i2605.DCE",
        setting={"fast_window": 10, "slow_window": 20}
    ),
    # 化工
    StrategyConfig(
        class_name="DoubleMaStrategy",
        strategy_name="双均线_甲醇",
        vt_symbol="MA605.CZCE",
        setting={"fast_window": 10, "slow_window": 20}
    ),
    StrategyConfig(
        class_name="DoubleMaStrategy",
        strategy_name="双均线_纯碱",
        vt_symbol="SA605.CZCE",
        setting={"fast_window": 10, "slow_window": 20}
    ),
    # 农产品
    StrategyConfig(
        class_name="DoubleMaStrategy",
        strategy_name="双均线_棕榈",
        vt_symbol="p2605.DCE",
        setting={"fast_window": 10, "slow_window": 20}
    ),
]

# ============================================================
# 行情落库配置
# ============================================================
RECORD_BAR_DATA = True
BAR_FLUSH_SIZE = 10           # 批量写入阈值，每10根K线写入一次
BAR_FLUSH_INTERVAL = 60       # 强制刷新间隔（秒）

# ============================================================
# 交易时段定义（国内期货）
# ============================================================
DAY_START = time(8, 45)
DAY_END = time(15, 0)
NIGHT_START = time(20, 45)
NIGHT_END = time(2, 45)


def check_trading_period() -> bool:
    """检查当前是否在交易时段内"""
    current_time = datetime.now().time()
    is_day_session = DAY_START <= current_time <= DAY_END
    is_night_session = current_time >= NIGHT_START or current_time <= NIGHT_END
    return is_day_session or is_night_session


def validate_config() -> bool:
    """校验配置是否已填写"""
    if not CTP_SETTING["用户名"] or not CTP_SETTING["密码"]:
        logger.error("=" * 60)
        logger.error("请先在脚本中填写 SimNow 账号信息！")
        logger.error("  可通过环境变量 SIMNOW_USER/SIMNOW_PASSWORD 设置")
        logger.error("=" * 60)
        return False
    return True


class MultiBarRecorder:
    """
    多品种K线记录器
    - 为每个品种维护独立的BarGenerator
    - 批量写入数据库，减少SQLite锁竞争
    """

    def __init__(self, database: BaseDatabase, flush_size: int = BAR_FLUSH_SIZE) -> None:
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
        if elapsed >= BAR_FLUSH_INTERVAL:
            self.flush()

    def get_summary(self) -> Dict[str, int]:
        """获取各品种的K线统计"""
        return self.bar_counts.copy()


def validate_contracts(main_engine: MainEngine, configs: List[StrategyConfig]) -> List[StrategyConfig]:
    """
    验证合约是否可用，返回有效的配置列表
    """
    valid_configs = []
    all_contracts = main_engine.get_all_contracts()
    available_symbols = {c.vt_symbol for c in all_contracts}
    
    logger.info("=" * 60)
    logger.info("合约验证")
    logger.info("=" * 60)
    
    for config in configs:
        if config.vt_symbol in available_symbols:
            contract = main_engine.get_contract(config.vt_symbol)
            logger.info(f"[✓] {config.vt_symbol:20} | {contract.name if contract else 'Unknown'}")
            valid_configs.append(config)
        else:
            logger.warning(f"[✗] {config.vt_symbol:20} | 合约不可用")
    
    # 如果所有合约都无效，列出一些可用合约供参考
    if not valid_configs and all_contracts:
        logger.warning("没有可用的合约，以下是部分可用合约示例:")
        samples = [c.vt_symbol for c in all_contracts[:10]]
        for symbol in samples:
            logger.warning(f"  - {symbol}")
    
    logger.info("=" * 60)
    return valid_configs


def run(
    check_connection: bool = False,
    wait_seconds: int = 25,
    record_bars: bool = RECORD_BAR_DATA,
    strategy_pool: Optional[List[StrategyConfig]] = None
) -> None:
    """
    启动多品种模拟交易
    
    Args:
        check_connection: 仅检查连接
        wait_seconds: 等待合约下载时间
        record_bars: 是否记录K线
        strategy_pool: 策略池配置，默认使用TRADING_POOL
    """
    configs = strategy_pool or TRADING_POOL
    
    if not validate_config():
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("SimNow 仿真交易系统启动 [多品种交易池]")
    logger.info(f"交易品种数: {len(configs)}")
    for cfg in configs:
        logger.info(f"  - {cfg.vt_symbol}: {cfg.strategy_name}")
    logger.info("=" * 60)

    # 1. 创建事件引擎和主引擎
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    logger.info("主引擎创建成功")

    # 2. 添加 CTP 交易接口
    main_engine.add_gateway(CtpGateway)
    logger.info("CTP 网关添加成功")

    # 3. 添加 CTA 策略应用
    cta_engine: CtaEngine = main_engine.add_app(CtaStrategyApp)
    logger.info("CTA 策略引擎添加成功")

    # 4. 注册 CTA 日志事件
    log_engine: LogEngine = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    logger.info("日志事件监听注册完成")

    # 5. 设置多品种K线记录
    tick_counters: Dict[str, dict] = {}
    bar_recorder: Optional[MultiBarRecorder] = None
    
    if record_bars and not check_connection:
        database = get_database()
        bar_recorder = MultiBarRecorder(database)
        for cfg in configs:
            bar_recorder.register_symbol(cfg.vt_symbol)
            tick_counters[cfg.vt_symbol] = {"count": 0, "last_time": None}
        logger.info(f"多品种K线落库已启用，共 {len(configs)} 个品种")

    def on_tick_diagnostic(event: Event) -> None:
        """统一的Tick处理回调"""
        tick: TickData = event.data
        vt_symbol = tick.vt_symbol
        
        # 更新计数器
        if vt_symbol in tick_counters:
            tick_counters[vt_symbol]["count"] += 1
            tick_counters[vt_symbol]["last_time"] = tick.datetime
        
        # K线记录
        if bar_recorder:
            bar_recorder.on_tick(tick)
        
        # 打印诊断信息（每个品种前5个Tick）
        if vt_symbol in tick_counters:
            count = tick_counters[vt_symbol]["count"]
            if count <= 5:
                logger.info(
                    f"[Tick] {vt_symbol} | 第{count}个 | "
                    f"最新价={tick.last_price} | 时间={tick.datetime}"
                )

    # 注册所有品种的Tick事件
    for cfg in configs:
        event_engine.register(EVENT_TICK + cfg.vt_symbol, on_tick_diagnostic)
        logger.info(f"已订阅行情: {cfg.vt_symbol}")

    # 6. 连接 SimNow CTP 仿真服务器
    main_engine.connect(CTP_SETTING, "CTP")
    logger.info("正在连接 SimNow CTP 仿真服务器...")
    logger.info(f"等待连接建立和合约数据下载（约 {wait_seconds} 秒）...")
    sleep(wait_seconds)

    # 7. 验证合约
    valid_configs = validate_contracts(main_engine, configs)
    
    if not valid_configs:
        logger.error("没有可用的合约，无法启动策略")
        main_engine.close()
        sys.exit(1)
    
    if check_connection:
        logger.info("连接检查模式结束，不启动 CTA 策略。")
        main_engine.close()
        return

    # 8. 初始化 CTA 策略引擎
    cta_engine.init_engine()
    logger.info("CTA 策略引擎初始化完成")

    # 9. 添加所有策略实例
    for cfg in valid_configs:
        cta_engine.add_strategy(
            class_name=cfg.class_name,
            strategy_name=cfg.strategy_name,
            vt_symbol=cfg.vt_symbol,
            setting=cfg.setting,
        )
        logger.info(f"策略 [{cfg.strategy_name}] 添加成功")

    # 10. 初始化所有策略
    for cfg in valid_configs:
        cta_engine.init_strategy(cfg.strategy_name)
        logger.info(f"策略 [{cfg.strategy_name}] 初始化中...")
    
    sleep(10)  # 等待策略初始化完成
    logger.info("所有策略初始化完成")

    # 11. 启动所有策略
    for cfg in valid_configs:
        cta_engine.start_strategy(cfg.strategy_name)
        logger.info(f"策略 [{cfg.strategy_name}] 已启动运行！")

    logger.info("=" * 60)
    logger.info(f"多品种交易池运行中（共 {len(valid_configs)} 个策略）")
    logger.info("按 Ctrl+C 停止...")
    logger.info("=" * 60)

    # 12. 主循环：监控所有策略状态
    try:
        while True:
            sleep(10)
            
            # 强制刷新K线缓存
            if bar_recorder:
                bar_recorder.check_force_flush()
            
            # 收集所有策略状态
            total_ticks = sum(c["count"] for c in tick_counters.values())
            active_strategies = 0
            warming_strategies = 0
            
            for cfg in valid_configs:
                strategy = cta_engine.strategies.get(cfg.strategy_name)
                if not strategy:
                    continue
                
                if hasattr(strategy, "am") and strategy.am.inited:
                    active_strategies += 1
                else:
                    warming_strategies += 1
            
            # 打印整体状态
            if warming_strategies > 0:
                logger.info(
                    f"[状态] 预热中: {warming_strategies} | "
                    f"运行中: {active_strategies} | "
                    f"总Tick: {total_ticks}"
                )
            else:
                # 所有策略就绪，打印详细信息
                pos_summary = []
                for cfg in valid_configs:
                    strategy = cta_engine.strategies.get(cfg.strategy_name)
                    if strategy:
                        pos = getattr(strategy, "pos", 0)
                        if pos != 0:
                            pos_summary.append(f"{cfg.strategy_name}={pos}")
                
                pos_str = " | ".join(pos_summary) if pos_summary else "全部空仓"
                logger.info(f"[运行中] 持仓: {pos_str} | 总Tick: {total_ticks}")

    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")

    # 13. 清理退出
    if bar_recorder:
        bar_recorder.flush()
        summary = bar_recorder.get_summary()
        logger.info("=" * 60)
        logger.info("K线落库统计:")
        for symbol, count in summary.items():
            logger.info(f"  {symbol}: {count} 根")
        logger.info("=" * 60)

    main_engine.close()
    logger.info("多品种模拟交易系统已安全关闭")


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="SimNow CTP 仿真交易启动脚本 - 多品种交易池")
    parser.add_argument(
        "--check-connection",
        action="store_true",
        help="只检查 CTP 连接和合约下载，不启动 CTA 策略",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=25,
        help="连接后等待合约下载的秒数，默认 25",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="运行策略但不把实时 Tick 合成 1分钟K线写入数据库",
    )
    parser.add_argument(
        "--pool",
        type=str,
        choices=["trend", "stable", "aggressive"],
        default="trend",
        help="选择预设交易池: trend(趋势型), stable(稳健型), aggressive(激进型)",
    )
    return parser.parse_args()


def get_preset_pool(pool_name: str) -> List[StrategyConfig]:
    """获取预设交易池"""
    pools = {
        "trend": TRADING_POOL,  # 默认趋势组合
        "stable": [
            # 稳健型组合 - 低波动品种
            StrategyConfig("DoubleMaStrategy", "双均线_黄金", "au2606.SHFE", {"fast_window": 10, "slow_window": 20}),
            StrategyConfig("DoubleMaStrategy", "双均线_铝", "al2606.SHFE", {"fast_window": 10, "slow_window": 20}),
            StrategyConfig("DoubleMaStrategy", "双均线_玉米", "c2605.DCE", {"fast_window": 10, "slow_window": 20}),
            StrategyConfig("DoubleMaStrategy", "双均线_国债", "T2606.CFFEX", {"fast_window": 10, "slow_window": 20}),
        ],
        "aggressive": [
            # 激进型组合 - 高波动品种
            StrategyConfig("DoubleMaStrategy", "双均线_白银", "ag2606.SHFE", {"fast_window": 5, "slow_window": 10}),
            StrategyConfig("DoubleMaStrategy", "双均线_镍", "ni2606.SHFE", {"fast_window": 5, "slow_window": 10}),
            StrategyConfig("DoubleMaStrategy", "双均线_纯碱", "SA606.CZCE", {"fast_window": 5, "slow_window": 10}),
            StrategyConfig("DoubleMaStrategy", "双均线_铁矿", "i2606.DCE", {"fast_window": 5, "slow_window": 10}),
        ],
    }
    return pools.get(pool_name, TRADING_POOL)


if __name__ == "__main__":
    args = parse_args()
    
    # 选择交易池
    selected_pool = get_preset_pool(args.pool)
    logger.info(f"使用交易池: {args.pool} ({len(selected_pool)} 个品种)")
    
    run(
        check_connection=args.check_connection,
        wait_seconds=args.wait,
        record_bars=not args.no_record,
        strategy_pool=selected_pool,
    )
