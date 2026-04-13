"""
数据库行情数据可视化工具
- 读取本地 SQLite 数据库中已录制的 K 线数据
- 生成交互式 K 线图（HTML 文件，浏览器打开）
- 支持查看数据库概览、指定合约和时间范围
- 支持叠加均线指标

用法：
    # 查看数据库中所有已录制数据的概览
    python3 visualize_data.py --overview

    # 可视化指定合约的全部数据
    python3 visualize_data.py --symbol rb2610.SHFE

    # 可视化指定合约和时间范围
    python3 visualize_data.py --symbol rb2610.SHFE --start 2026-04-01 --end 2026-04-13

    # 可视化并叠加均线
    python3 visualize_data.py --symbol rb2610.SHFE --ma 10,20

    # 指定输出文件名
    python3 visualize_data.py --symbol rb2610.SHFE --output my_chart.html
"""
import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy.trader.database import get_database, BaseDatabase


def show_overview(database: BaseDatabase) -> None:
    """显示数据库中所有已录制数据的概览"""
    overviews = database.get_bar_overview()

    if not overviews:
        print("数据库中暂无任何 K 线数据。")
        print("请先运行 run_recorder.py 录制行情数据，或运行 run_backtest.py 生成模拟数据。")
        return

    print("=" * 80)
    print("数据库 K 线数据概览")
    print("=" * 80)
    print(f"{'合约':<20} {'周期':<8} {'起始时间':<22} {'结束时间':<22} {'数据量':>8}")
    print("-" * 80)

    for overview in overviews:
        vt_symbol = f"{overview.symbol}.{overview.exchange.value}"
        print(
            f"{vt_symbol:<20} "
            f"{overview.interval.value:<8} "
            f"{overview.start.strftime('%Y-%m-%d %H:%M'):<22} "
            f"{overview.end.strftime('%Y-%m-%d %H:%M'):<22} "
            f"{overview.count:>8}"
        )

    print("=" * 80)


def load_bars_as_dataframe(
    database: BaseDatabase,
    symbol: str,
    exchange: Exchange,
    interval: Interval,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """从数据库加载 K 线数据并转为 DataFrame"""
    bars: list[BarData] = database.load_bar_data(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        start=start,
        end=end,
    )

    if not bars:
        return pd.DataFrame()

    data = []
    for bar in bars:
        data.append({
            "datetime": bar.datetime,
            "open": bar.open_price,
            "high": bar.high_price,
            "low": bar.low_price,
            "close": bar.close_price,
            "volume": bar.volume,
            "turnover": bar.turnover,
            "open_interest": bar.open_interest,
        })

    dataframe = pd.DataFrame(data)
    dataframe.set_index("datetime", inplace=True)
    dataframe.sort_index(inplace=True)
    return dataframe


def generate_candlestick_chart(
    dataframe: pd.DataFrame,
    vt_symbol: str,
    ma_periods: list[int] | None = None,
    output_path: str = "kline_chart.html",
) -> str:
    """
    生成交互式 K 线图（Candlestick + 成交量 + 均线）
    输出为 HTML 文件
    """
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=[f"{vt_symbol} K线图", "成交量"],
    )

    # K 线图
    fig.add_trace(
        go.Candlestick(
            x=dataframe.index,
            open=dataframe["open"],
            high=dataframe["high"],
            low=dataframe["low"],
            close=dataframe["close"],
            name="K线",
            increasing_line_color="#ef5350",     # 阳线红色
            decreasing_line_color="#26a69a",     # 阴线绿色
            increasing_fillcolor="#ef5350",
            decreasing_fillcolor="#26a69a",
        ),
        row=1,
        col=1,
    )

    # 均线
    ma_colors = ["#FF9800", "#2196F3", "#9C27B0", "#4CAF50", "#F44336"]
    if ma_periods:
        for index, period in enumerate(ma_periods):
            if len(dataframe) >= period:
                ma_values = dataframe["close"].rolling(window=period).mean()
                color = ma_colors[index % len(ma_colors)]
                fig.add_trace(
                    go.Scatter(
                        x=dataframe.index,
                        y=ma_values,
                        mode="lines",
                        name=f"MA{period}",
                        line=dict(width=1.5, color=color),
                    ),
                    row=1,
                    col=1,
                )

    # 成交量柱状图（阳线红色，阴线绿色）
    colors = [
        "#ef5350" if close >= open_price else "#26a69a"
        for close, open_price in zip(dataframe["close"], dataframe["open"])
    ]
    fig.add_trace(
        go.Bar(
            x=dataframe.index,
            y=dataframe["volume"],
            name="成交量",
            marker_color=colors,
            opacity=0.7,
        ),
        row=2,
        col=1,
    )

    # 图表样式
    start_time = dataframe.index[0].strftime("%Y-%m-%d")
    end_time = dataframe.index[-1].strftime("%Y-%m-%d")
    ma_label = ""
    if ma_periods:
        ma_label = " | MA: " + ",".join(str(p) for p in ma_periods)

    fig.update_layout(
        title=dict(
            text=f"{vt_symbol}  ({start_time} ~ {end_time} | {len(dataframe)} 根K线{ma_label})",
            x=0.5,
        ),
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=800,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    fig.update_xaxes(title_text="时间", row=2, col=1)
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)

    fig.write_html(output_path)
    return output_path


def print_data_summary(dataframe: pd.DataFrame, vt_symbol: str) -> None:
    """打印数据统计摘要"""
    if dataframe.empty:
        return

    print(f"\n{'=' * 60}")
    print(f"数据统计摘要: {vt_symbol}")
    print(f"{'=' * 60}")
    print(f"  数据量:     {len(dataframe)} 根K线")
    print(f"  时间范围:   {dataframe.index[0]} ~ {dataframe.index[-1]}")
    print(f"  最高价:     {dataframe['high'].max():.1f}")
    print(f"  最低价:     {dataframe['low'].min():.1f}")
    print(f"  开盘价:     {dataframe['open'].iloc[0]:.1f}")
    print(f"  收盘价:     {dataframe['close'].iloc[-1]:.1f}")
    price_change = dataframe["close"].iloc[-1] - dataframe["open"].iloc[0]
    price_change_pct = price_change / dataframe["open"].iloc[0] * 100
    print(f"  涨跌幅:     {price_change:+.1f} ({price_change_pct:+.2f}%)")
    print(f"  总成交量:   {dataframe['volume'].sum():,.0f}")
    print(f"{'=' * 60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="数据库行情数据可视化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 visualize_data.py --overview
  python3 visualize_data.py --symbol rb2610.SHFE
  python3 visualize_data.py --symbol rb2610.SHFE --start 2026-01-01 --end 2026-04-01
  python3 visualize_data.py --symbol rb2610.SHFE --ma 10,20
        """,
    )
    parser.add_argument("--overview", action="store_true", help="显示数据库中所有数据的概览")
    parser.add_argument("--symbol", type=str, help="合约代码，格式: rb2610.SHFE")
    parser.add_argument("--start", type=str, help="起始日期，格式: 2026-01-01")
    parser.add_argument("--end", type=str, help="结束日期，格式: 2026-04-01")
    parser.add_argument("--ma", type=str, help="均线周期，逗号分隔，如: 10,20,60")
    parser.add_argument("--interval", type=str, default="1m", help="K线周期 (默认: 1m)")
    parser.add_argument("--output", type=str, default="kline_chart.html", help="输出HTML文件路径 (默认: kline_chart.html)")

    args = parser.parse_args()
    database = get_database()

    # 模式1：数据概览
    if args.overview:
        show_overview(database)
        return

    # 模式2：可视化指定合约
    if not args.symbol:
        # 无参数时默认显示概览
        show_overview(database)
        print("\n提示: 使用 --symbol 参数指定合约进行可视化")
        print("例如: python3 visualize_data.py --symbol rb2610.SHFE --ma 10,20")
        return

    # 解析合约代码
    if "." not in args.symbol:
        print(f"错误: 合约代码格式不正确，应为 '合约代码.交易所'，如 rb2610.SHFE")
        sys.exit(1)

    symbol, exchange_str = args.symbol.split(".")
    exchange = Exchange(exchange_str)
    interval = Interval(args.interval)

    # 解析时间范围
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start = datetime(2000, 1, 1)

    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d")
    else:
        end = datetime.now() + timedelta(days=1)

    # 解析均线参数
    ma_periods = None
    if args.ma:
        ma_periods = [int(p.strip()) for p in args.ma.split(",")]

    # 加载数据
    print(f"正在从数据库加载 {args.symbol} 的 K 线数据...")
    dataframe = load_bars_as_dataframe(database, symbol, exchange, interval, start, end)

    if dataframe.empty:
        print(f"未找到 {args.symbol} 在 {start.date()} ~ {end.date()} 的数据。")
        print("请先运行 run_recorder.py 录制数据，或运行 run_backtest.py 生成模拟数据。")
        show_overview(database)
        return

    # 打印统计摘要
    print_data_summary(dataframe, args.symbol)

    # 生成图表
    print(f"\n正在生成 K 线图...")
    output_path = generate_candlestick_chart(
        dataframe=dataframe,
        vt_symbol=args.symbol,
        ma_periods=ma_periods,
        output_path=args.output,
    )
    print(f"K 线图已生成: {output_path}")
    print(f"请在浏览器中打开查看（或使用 VSCode 的 Live Preview 插件）")


if __name__ == "__main__":
    import sys
    main()
