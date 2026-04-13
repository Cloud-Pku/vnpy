"""
双均线策略本地回测脚本
- 自动生成模拟 K 线数据（模拟螺纹钢走势）
- 使用 BacktestingEngine 进行回测
- 输出完整的策略统计指标
- 无需连接外部服务器，纯本地运行
"""
from datetime import datetime, timedelta
import random

import numpy as np
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy.trader.database import get_database, DB_TZ
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy


def generate_simulated_bars(
    symbol: str,
    exchange: Exchange,
    start: datetime,
    end: datetime,
    initial_price: float = 3800.0,
) -> list[BarData]:
    """
    生成模拟的分钟级 K 线数据（模拟螺纹钢走势特征）

    使用几何布朗运动 + 均值回归，模拟真实期货价格波动：
    - 日内波动率约 0.5%-1.5%
    - 带有趋势性（适合均线策略测试）
    - 价格在合理区间内波动
    """
    bars: list[BarData] = []
    price = initial_price
    current_time = start

    # 随机种子保证可复现
    random.seed(42)
    np.random.seed(42)

    # 模拟参数
    mean_price = initial_price
    mean_reversion_speed = 0.001
    volatility = 0.0008
    trend_strength = 0.0001

    # 生成趋势序列（模拟几段上涨/下跌趋势）
    total_minutes = int((end - start).total_seconds() / 60)
    trend_changes = np.cumsum(np.random.randn(total_minutes // 500 + 1)) * trend_strength

    minute_count = 0

    while current_time < end:
        # 跳过非交易时段（简化：只保留 9:00-15:00 的日盘）
        hour = current_time.hour
        weekday = current_time.weekday()

        if weekday >= 5 or hour < 9 or hour >= 15:
            current_time += timedelta(minutes=1)
            continue

        # 跳过午休 11:30-13:30
        if (hour == 11 and current_time.minute >= 30) or hour == 12 or (hour == 13 and current_time.minute < 30):
            current_time += timedelta(minutes=1)
            continue

        # 计算当前趋势
        trend_index = min(minute_count // 500, len(trend_changes) - 1)
        current_trend = trend_changes[trend_index]

        # 价格变动 = 趋势 + 均值回归 + 随机波动
        mean_reversion = mean_reversion_speed * (mean_price - price) / mean_price
        random_shock = np.random.randn() * volatility
        price_change = price * (current_trend + mean_reversion + random_shock)
        price += price_change

        # 确保价格为正且在合理范围
        price = max(price, initial_price * 0.7)
        price = min(price, initial_price * 1.3)

        # 生成 OHLC（价格对齐到 pricetick=1，即整数）
        intra_vol = abs(np.random.randn()) * volatility * price
        open_price = round(price + np.random.randn() * intra_vol * 0.3)
        high_price = round(max(price, open_price) + abs(np.random.randn()) * intra_vol)
        low_price = round(min(price, open_price) - abs(np.random.randn()) * intra_vol)
        close_price = round(price)

        # 确保 high >= open/close >= low
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)

        # datetime 需要带时区信息，与数据库时区一致
        bar_datetime = current_time.replace(tzinfo=DB_TZ)

        bar = BarData(
            symbol=symbol,
            exchange=exchange,
            datetime=bar_datetime,
            interval=Interval.MINUTE,
            volume=float(random.randint(500, 5000)),
            turnover=float(random.randint(1000000, 50000000)),
            open_interest=float(random.randint(100000, 500000)),
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            gateway_name="BACKTESTING",
        )
        bars.append(bar)

        current_time += timedelta(minutes=1)
        minute_count += 1

    return bars


def run_backtest() -> None:
    """运行双均线策略回测"""
    symbol = "rb2610"
    exchange = Exchange.SHFE
    vt_symbol = f"{symbol}.{exchange.value}"

    start_date = datetime(2025, 10, 1)
    end_date = datetime(2026, 3, 31)

    print("=" * 60)
    print("双均线策略（DoubleMaStrategy）回测")
    print("=" * 60)
    print(f"交易品种: {vt_symbol} (螺纹钢)")
    print(f"回测区间: {start_date.date()} ~ {end_date.date()}")
    print(f"策略参数: fast_window=10, slow_window=20")
    print("=" * 60)

    # 第一步：生成模拟数据并写入数据库
    print("\n[1/4] 生成模拟 K 线数据...")
    bars = generate_simulated_bars(symbol, exchange, start_date, end_date)
    print(f"  生成 {len(bars)} 条分钟 K 线数据")

    print("\n[2/4] 写入本地数据库...")
    database = get_database()
    database.save_bar_data(bars)
    print("  数据写入完成")

    # 第二步：配置回测引擎
    print("\n[3/4] 配置回测引擎...")
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval="1m",
        start=start_date,
        end=end_date,
        rate=1 / 10000,         # 螺纹钢手续费约万分之一
        slippage=1,             # 滑点 1 元
        size=10,                # 螺纹钢合约乘数 10 吨/手
        pricetick=1,            # 最小价格变动 1 元
        capital=100_000,        # 初始资金 10 万
    )
    engine.add_strategy(DoubleMaStrategy, {
        "fast_window": 10,
        "slow_window": 20,
    })
    print("  回测引擎配置完成")

    # 第三步：运行回测
    print("\n[4/4] 开始运行回测...")
    print("-" * 60)
    engine.load_data()
    engine.run_backtesting()
    result_df = engine.calculate_result()
    statistics = engine.calculate_statistics()
    print("-" * 60)

    # 第四步：输出结果
    if statistics:
        print("\n" + "=" * 60)
        print("回测结果统计")
        print("=" * 60)
        for key, value in statistics.items():
            print(f"  {key}: {value}")

    # 输出交易记录摘要
    trades = engine.get_all_trades()
    print(f"\n总交易笔数: {len(trades)}")
    if trades:
        print("\n最近 10 笔交易:")
        print(f"  {'时间':<20} {'方向':<6} {'开平':<6} {'价格':<10} {'数量':<6}")
        print("  " + "-" * 48)
        for trade in trades[-10:]:
            print(
                f"  {trade.datetime.strftime('%Y-%m-%d %H:%M'):<20} "
                f"{trade.direction.value:<6} "
                f"{trade.offset.value:<6} "
                f"{trade.price:<10.1f} "
                f"{trade.volume:<6.0f}"
            )

    print("\n" + "=" * 60)
    print("回测完成！")
    print("=" * 60)


if __name__ == "__main__":
    run_backtest()
