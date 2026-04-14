"""
独立行情录制入口
- 连接 SimNow CTP 仿真服务器
- 订阅指定合约的 Tick 行情
- 实时将 Tick 合成 1 分钟 K 线并持久化到本地数据库
- 支持同时录制多个合约
- 独立运行，不依赖 vnpy_datarecorder 模块
"""
import sys
from time import sleep
from datetime import datetime
from collections.abc import Callable

from vnpy.event import Event, EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import TickData, BarData, SubscribeRequest, ContractData
from vnpy.trader.event import EVENT_TICK
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.utility import BarGenerator
from vnpy.trader.database import get_database, BaseDatabase
from vnpy.trader.logger import INFO, logger

from vnpy_ctp import CtpGateway


# ============================================================
# 全局配置
# ============================================================
SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True

# ============================================================
# SimNow CTP 连接配置（与 run_sim.py 保持一致）
# ============================================================
CTP_SETTING = {
    "用户名": "258545",           # SimNow 账号（手机号）
    "密码": "!CzhCy1124",             # SimNow 密码
    "经纪商代码": "9999",
    "交易服务器": "182.254.243.31:40001",
    "行情服务器": "182.254.243.31:40011",
    "产品名称": "simnow_client_test",
    "授权编码": "0000000000000000",
    "柜台环境": "测试",
}

# ============================================================
# 录制配置：要录制的合约列表
# 格式：合约代码.交易所
# ============================================================
RECORDING_SYMBOLS = [
    "rb2610.SHFE",      # 螺纹钢
    # "IF2606.CFFEX",   # 沪深300股指期货（按需取消注释）
    # "ag2612.SHFE",    # 白银（按需取消注释）
]

# 数据库批量写入间隔（每积累多少根 K 线写入一次）
BATCH_FLUSH_SIZE = 1


class BarRecorder:
    """
    K 线录制器
    - 为每个合约维护一个 BarGenerator，将 Tick 合成 1 分钟 K 线
    - 合成完毕后立即写入数据库
    """

    def __init__(self, database: BaseDatabase) -> None:
        self.database: BaseDatabase = database
        self.bar_generators: dict[str, BarGenerator] = {}
        self.bar_buffers: dict[str, list[BarData]] = {}
        self.bar_counts: dict[str, int] = {}

    def add_symbol(self, vt_symbol: str) -> None:
        """为指定合约创建 BarGenerator"""
        callback: Callable = self._make_on_bar_callback(vt_symbol)
        self.bar_generators[vt_symbol] = BarGenerator(callback)
        self.bar_buffers[vt_symbol] = []
        self.bar_counts[vt_symbol] = 0
        logger.info(f"[录制器] 添加合约: {vt_symbol}")

    def _make_on_bar_callback(self, vt_symbol: str) -> Callable:
        """为每个合约生成独立的 on_bar 回调"""
        def on_bar(bar: BarData) -> None:
            self.bar_counts[vt_symbol] = self.bar_counts.get(vt_symbol, 0) + 1
            self.bar_buffers[vt_symbol].append(bar)

            # 达到批量写入阈值时刷入数据库
            if len(self.bar_buffers[vt_symbol]) >= BATCH_FLUSH_SIZE:
                self._flush_bars(vt_symbol)

            count = self.bar_counts[vt_symbol]
            logger.info(
                f"[录制] {vt_symbol} | "
                f"{bar.datetime.strftime('%Y-%m-%d %H:%M')} | "
                f"O={bar.open_price:.1f} H={bar.high_price:.1f} "
                f"L={bar.low_price:.1f} C={bar.close_price:.1f} "
                f"V={bar.volume:.0f} | 累计 {count} 根K线"
            )
        return on_bar

    def _flush_bars(self, vt_symbol: str) -> None:
        """将缓冲区中的 K 线写入数据库"""
        bars = self.bar_buffers[vt_symbol]
        if not bars:
            return

        self.database.save_bar_data(bars, stream=True)
        self.bar_buffers[vt_symbol] = []

    def flush_all(self) -> None:
        """刷入所有缓冲区"""
        for vt_symbol in self.bar_buffers:
            self._flush_bars(vt_symbol)

    def on_tick(self, tick: TickData) -> None:
        """处理 Tick 数据，转发给对应的 BarGenerator"""
        vt_symbol = tick.vt_symbol
        generator = self.bar_generators.get(vt_symbol)
        if generator:
            generator.update_tick(tick)

    def get_status(self) -> dict[str, int]:
        """获取各合约已录制的 K 线数量"""
        return dict(self.bar_counts)


def validate_config() -> bool:
    """校验配置是否已填写"""
    if not CTP_SETTING["用户名"] or not CTP_SETTING["密码"]:
        logger.error("=" * 60)
        logger.error("请先填写 SimNow 账号信息！")
        logger.error("  CTP_SETTING['用户名'] = 你的SimNow账号")
        logger.error("  CTP_SETTING['密码']   = 你的SimNow密码")
        logger.error("=" * 60)
        return False

    if not RECORDING_SYMBOLS:
        logger.error("RECORDING_SYMBOLS 为空，请至少配置一个要录制的合约")
        return False

    return True


def run() -> None:
    """启动行情录制"""
    if not validate_config():
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("行情录制系统启动")
    logger.info(f"录制合约: {', '.join(RECORDING_SYMBOLS)}")
    logger.info("=" * 60)

    # 1. 初始化数据库和录制器
    database = get_database()
    recorder = BarRecorder(database)

    for vt_symbol in RECORDING_SYMBOLS:
        recorder.add_symbol(vt_symbol)

    # 2. 创建引擎
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(CtpGateway)
    logger.info("主引擎和 CTP 网关创建成功")

    # 3. 注册 Tick 事件处理
    def on_tick_event(event: Event) -> None:
        tick: TickData = event.data
        recorder.on_tick(tick)

    for vt_symbol in RECORDING_SYMBOLS:
        event_engine.register(EVENT_TICK + vt_symbol, on_tick_event)
    logger.info("Tick 事件监听注册完成")

    # 4. 连接 SimNow
    main_engine.connect(CTP_SETTING, "CTP")
    logger.info("正在连接 SimNow CTP 仿真服务器...")
    logger.info("等待连接建立和合约数据下载（约 20 秒）...")
    sleep(20)

    # 5. 订阅行情
    for vt_symbol in RECORDING_SYMBOLS:
        symbol, exchange_str = vt_symbol.split(".")
        exchange = Exchange(exchange_str)

        contract: ContractData | None = main_engine.get_contract(vt_symbol)
        if contract:
            req = SubscribeRequest(symbol=contract.symbol, exchange=contract.exchange)
            main_engine.subscribe(req, "CTP")
            logger.info(f"已订阅行情: {vt_symbol} ({contract.name})")
        else:
            # 合约信息可能还没下载完，直接用配置的信息订阅
            req = SubscribeRequest(symbol=symbol, exchange=exchange)
            main_engine.subscribe(req, "CTP")
            logger.info(f"已订阅行情: {vt_symbol} (合约信息未获取，使用手动配置)")

    logger.info("=" * 60)
    logger.info("行情录制运行中，按 Ctrl+C 停止...")
    logger.info("数据将实时写入本地 SQLite 数据库")
    logger.info("=" * 60)

    # 6. 主循环：保持运行，定期打印状态
    try:
        while True:
            sleep(60)

            status = recorder.get_status()
            status_lines = [f"{sym}: {cnt} 根K线" for sym, cnt in status.items()]
            logger.info(f"[录制状态] {' | '.join(status_lines)}")

    except KeyboardInterrupt:
        logger.info("收到停止信号，正在刷入剩余数据...")

    # 7. 清理退出
    recorder.flush_all()
    main_engine.close()
    logger.info("行情录制系统已安全关闭，所有数据已持久化")


if __name__ == "__main__":
    run()
