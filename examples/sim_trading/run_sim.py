"""
SimNow 仿真交易启动脚本（No-UI 模式）
- 连接 SimNow CTP 仿真服务器
- 使用双均线策略（DoubleMaStrategy）交易螺纹钢
- 纯命令行运行，无需 GUI
"""
import argparse
import os
import sys
from time import sleep
from datetime import datetime, time

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
# 请填入你的 SimNow 账号信息
# 注册地址：https://www.simnow.com.cn/
# ============================================================
CTP_SETTING = {
    # SimNow 登录用户名应填写 6 位 InvestorID，不是网页登录手机号。
    # 可通过环境变量 SIMNOW_USER/SIMNOW_PASSWORD 覆盖，避免把密码写在脚本里。
    "用户名": "258545",
    "密码": "!CzhCy1124",
    "经纪商代码": "9999",
    # SimNow CTP 仿真前置。可通过环境变量切换其他前置地址。
    "交易服务器": os.getenv("SIMNOW_TD_ADDRESS", "182.254.243.31:30001"),
    "行情服务器": os.getenv("SIMNOW_MD_ADDRESS", "182.254.243.31:30011"),
    "产品名称": "simnow_client_test",
    "授权编码": "0000000000000000",
    "柜台环境": os.getenv("SIMNOW_ENVIRONMENT", "实盘"),
}

# ============================================================
# 策略配置
# vt_symbol 格式：合约代码.交易所
# 螺纹钢主力合约，请根据当前月份调整合约月份
# 例如 2026 年 10 月到期的合约为 rb2610
# ============================================================
STRATEGY_CONFIG = {
    "class_name": "DoubleMaStrategy",
    "strategy_name": "双均线策略_螺纹钢",
    "vt_symbol": "rb2610.SHFE",     # 请根据实际主力合约调整
    "setting": {
        "fast_window": 10,          # 快速均线周期
        "slow_window": 20,          # 慢速均线周期
    },
}

# ============================================================
# 行情落库配置
# ============================================================
RECORD_BAR_DATA = True
BAR_FLUSH_SIZE = 1

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
        logger.error("  CTP_SETTING['用户名'] = 你的SimNow账号")
        logger.error("  CTP_SETTING['密码']   = 你的SimNow密码")
        logger.error("SimNow 注册地址：https://www.simnow.com.cn/")
        logger.error("=" * 60)
        return False
    return True


class RuntimeBarRecorder:
    """把 run_sim.py 收到的 Tick 合成 1 分钟 K 线并写入数据库。"""

    def __init__(self, vt_symbol: str, database: BaseDatabase) -> None:
        self.vt_symbol = vt_symbol
        self.database = database
        self.buffer: list[BarData] = []
        self.bar_count = 0
        self.bg = BarGenerator(self.on_bar)

    def on_tick(self, tick: TickData) -> None:
        """处理 Tick 数据。"""
        if tick.vt_symbol != self.vt_symbol:
            return
        try:
            self.bg.update_tick(tick)
        except Exception:
            logger.exception("1分钟K线落库处理异常")

    @staticmethod
    def get_bar_vt_symbol(bar: BarData) -> str:
        """兼容不同 vn.py 版本的 BarData 交易所字段。"""
        exchange = getattr(bar.exchange, "value", bar.exchange)
        return f"{bar.symbol}.{exchange}"

    def on_bar(self, bar: BarData) -> None:
        """保存合成后的 1 分钟 K 线。"""
        self.bar_count += 1
        self.buffer.append(bar)

        if len(self.buffer) >= BAR_FLUSH_SIZE:
            self.flush()

        logger.info(
            f"[落库] {self.get_bar_vt_symbol(bar)} | {bar.datetime.strftime('%Y-%m-%d %H:%M')} | "
            f"O={bar.open_price:.1f} H={bar.high_price:.1f} "
            f"L={bar.low_price:.1f} C={bar.close_price:.1f} "
            f"V={bar.volume:.0f} | 累计 {self.bar_count} 根1分钟K线"
        )

    def flush(self) -> None:
        """刷入数据库。"""
        if not self.buffer:
            return

        self.database.save_bar_data(self.buffer, stream=True)
        self.buffer.clear()


def run(check_connection: bool = False, wait_seconds: int = 25, record_bars: bool = RECORD_BAR_DATA) -> None:
    """启动模拟交易"""
    # 校验配置
    if not validate_config():
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("SimNow 仿真交易系统启动")
    logger.info(f"交易品种: {STRATEGY_CONFIG['vt_symbol']}")
    logger.info(f"策略: {STRATEGY_CONFIG['class_name']}")
    logger.info(f"参数: fast_window={STRATEGY_CONFIG['setting']['fast_window']}, "
                f"slow_window={STRATEGY_CONFIG['setting']['slow_window']}")
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
    log_engine: LogEngine = main_engine.get_engine("log")       # type: ignore
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    logger.info("日志事件监听注册完成")

    # 5. 连接诊断：监控 Tick 接收情况
    tick_counter = {"count": 0, "last_tick_time": None, "last_tick_symbol": None}
    bar_recorder: RuntimeBarRecorder | None = None

    if record_bars and not check_connection:
        database = get_database()
        bar_recorder = RuntimeBarRecorder(STRATEGY_CONFIG["vt_symbol"], database)
        logger.info(f"1分钟K线落库已启用: {STRATEGY_CONFIG['vt_symbol']}")

    def on_tick_diagnostic(event: Event) -> None:
        tick: TickData = event.data
        tick_counter["count"] += 1
        tick_counter["last_tick_time"] = tick.datetime
        tick_counter["last_tick_symbol"] = tick.vt_symbol

        if bar_recorder:
            bar_recorder.on_tick(tick)

        # 前 5 个 Tick 打印详情，之后每 100 个打印一次
        if tick_counter["count"] <= 5 or tick_counter["count"] % 100 == 0:
            logger.info(
                f"[Tick诊断] 第{tick_counter['count']}个 | {tick.vt_symbol} | "
                f"最新价={tick.last_price} | 时间={tick.datetime}"
            )

    # 注册通用 Tick 事件（不带合约后缀，接收所有合约的 Tick）
    event_engine.register(EVENT_TICK + STRATEGY_CONFIG["vt_symbol"], on_tick_diagnostic)

    # 6. 连接 SimNow CTP 仿真服务器
    main_engine.connect(CTP_SETTING, "CTP")
    logger.info("正在连接 SimNow CTP 仿真服务器...")
    logger.info(f"等待连接建立和合约数据下载（约 {wait_seconds} 秒）...")
    sleep(wait_seconds)

    # 7. 连接诊断：检查合约信息
    vt_symbol = STRATEGY_CONFIG["vt_symbol"]
    contract = main_engine.get_contract(vt_symbol)
    if contract:
        logger.info(f"[诊断] 合约信息获取成功: {contract.name} ({vt_symbol})")
    else:
        logger.warning(f"[诊断] 未获取到合约 {vt_symbol} 的信息！")
        logger.warning("[诊断] 可能原因: 1) 合约代码不正确 2) 连接未成功 3) 合约数据未下载完")
        # 列出已获取的部分合约，帮助用户确认连接状态
        all_contracts = main_engine.get_all_contracts()
        if all_contracts:
            rb_contracts = [c for c in all_contracts if c.symbol.startswith("rb")]
            if rb_contracts:
                logger.info(f"[诊断] 可用的螺纹钢合约: {[c.vt_symbol for c in rb_contracts[:5]]}")
            else:
                sample = [c.vt_symbol for c in all_contracts[:10]]
                logger.info(f"[诊断] 已获取 {len(all_contracts)} 个合约，示例: {sample}")
        else:
            logger.error("[诊断] 未获取到任何合约信息，CTP 连接可能失败！")
            logger.error("[诊断] 请检查: 1) 用户名是否为 6 位 InvestorID 2) 账号密码是否正确 3) 网络是否可达 4) SimNow 是否在维护")

    if check_connection:
        logger.info("连接检查模式结束，不启动 CTA 策略。")
        main_engine.close()
        return

    # 8. 初始化 CTA 策略引擎
    cta_engine.init_engine()
    logger.info("CTA 策略引擎初始化完成")

    # 9. 添加策略实例
    cta_engine.add_strategy(
        class_name=STRATEGY_CONFIG["class_name"],
        strategy_name=STRATEGY_CONFIG["strategy_name"],
        vt_symbol=STRATEGY_CONFIG["vt_symbol"],
        setting=STRATEGY_CONFIG["setting"],
    )
    logger.info(f"策略 [{STRATEGY_CONFIG['strategy_name']}] 添加成功")

    # 10. 初始化策略（加载历史数据）
    cta_engine.init_strategy(STRATEGY_CONFIG["strategy_name"])
    sleep(10)   # 等待策略初始化完成
    logger.info(f"策略 [{STRATEGY_CONFIG['strategy_name']}] 初始化完成")

    # 11. 启动策略
    cta_engine.start_strategy(STRATEGY_CONFIG["strategy_name"])
    logger.info(f"策略 [{STRATEGY_CONFIG['strategy_name']}] 已启动运行！")

    logger.info("=" * 60)
    logger.info("模拟交易运行中，按 Ctrl+C 停止...")
    logger.info("=" * 60)

    # 12. 主循环：保持运行，监控状态
    try:
        while True:
            sleep(10)

            strategy = cta_engine.strategies.get(STRATEGY_CONFIG["strategy_name"])
            if not strategy:
                continue

            # 诊断：Tick 接收情况
            total_ticks = tick_counter["count"]

            # 检查 ArrayManager 预热状态
            if hasattr(strategy, "am") and not strategy.am.inited:
                bar_count = strategy.am.count
                bar_needed = strategy.am.size

                if total_ticks == 0:
                    logger.warning(
                        f"[诊断] 尚未收到任何 Tick 数据！"
                        f"可能原因: 1) 当前非交易时段 2) 合约代码不正确 3) 连接失败"
                    )
                else:
                    logger.info(
                        f"[预热中] K线进度: {bar_count}/{bar_needed} "
                        f"({bar_count * 100 // bar_needed}%) | "
                        f"已收到 {total_ticks} 个Tick | "
                        f"还需约 {bar_needed - bar_count} 根K线"
                    )
                continue

            # ArrayManager 已就绪，显示策略运行状态
            variables = strategy.get_variables()
            logger.info(
                f"[运行中] 持仓={variables.get('pos', 0)}, "
                f"fast_ma={variables.get('fast_ma0', 0):.2f}, "
                f"slow_ma={variables.get('slow_ma0', 0):.2f} | "
                f"累计Tick={total_ticks}"
            )

    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")

    # 11. 清理退出
    if bar_recorder:
        bar_recorder.flush()
        logger.info(f"1分钟K线落库结束，累计写入 {bar_recorder.bar_count} 根K线")

    main_engine.close()
    logger.info("模拟交易系统已安全关闭")


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="SimNow CTP 仿真交易启动脚本")
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        check_connection=args.check_connection,
        wait_seconds=args.wait,
        record_bars=not args.no_record,
    )
