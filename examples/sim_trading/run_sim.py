"""
SimNow 仿真交易启动脚本（No-UI 模式）
- 连接 SimNow CTP 仿真服务器
- 使用双均线策略（DoubleMaStrategy）交易螺纹钢
- 纯命令行运行，无需 GUI
"""
import sys
from time import sleep
from datetime import datetime, time

from vnpy.event import EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine, LogEngine
from vnpy.trader.logger import INFO, logger

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
    "用户名": "",           # SimNow 账号（手机号）
    "密码": "",             # SimNow 密码
    "经纪商代码": "9999",
    "交易服务器": "180.168.146.187:10202",   # 第二套（7x24h 可用）
    "行情服务器": "180.168.146.187:10212",   # 第二套（7x24h 可用）
    "产品名称": "simnow_client_test",
    "授权编码": "0000000000000000",
    "柜台环境": "测试",     # SimNow 为测试环境
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


def run() -> None:
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

    # 5. 连接 SimNow CTP 仿真服务器
    main_engine.connect(CTP_SETTING, "CTP")
    logger.info("正在连接 SimNow CTP 仿真服务器...")
    logger.info("等待连接建立和合约数据下载（约 20 秒）...")
    sleep(20)

    # 6. 初始化 CTA 策略引擎
    cta_engine.init_engine()
    logger.info("CTA 策略引擎初始化完成")

    # 7. 添加策略实例
    cta_engine.add_strategy(
        class_name=STRATEGY_CONFIG["class_name"],
        strategy_name=STRATEGY_CONFIG["strategy_name"],
        vt_symbol=STRATEGY_CONFIG["vt_symbol"],
        setting=STRATEGY_CONFIG["setting"],
    )
    logger.info(f"策略 [{STRATEGY_CONFIG['strategy_name']}] 添加成功")

    # 8. 初始化策略（加载历史数据）
    cta_engine.init_strategy(STRATEGY_CONFIG["strategy_name"])
    sleep(10)   # 等待策略初始化完成
    logger.info(f"策略 [{STRATEGY_CONFIG['strategy_name']}] 初始化完成")

    # 9. 启动策略
    cta_engine.start_strategy(STRATEGY_CONFIG["strategy_name"])
    logger.info(f"策略 [{STRATEGY_CONFIG['strategy_name']}] 已启动运行！")

    logger.info("=" * 60)
    logger.info("模拟交易运行中，按 Ctrl+C 停止...")
    logger.info("=" * 60)

    # 10. 主循环：保持运行，监控状态
    try:
        while True:
            sleep(10)

            # 获取策略状态并打印
            strategy = cta_engine.strategies.get(STRATEGY_CONFIG["strategy_name"])
            if strategy:
                variables = strategy.get_variables()
                logger.info(
                    f"[策略状态] 持仓={variables.get('pos', 0)}, "
                    f"fast_ma={variables.get('fast_ma0', 0):.2f}, "
                    f"slow_ma={variables.get('slow_ma0', 0):.2f}"
                )

    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")

    # 11. 清理退出
    main_engine.close()
    logger.info("模拟交易系统已安全关闭")


if __name__ == "__main__":
    run()
