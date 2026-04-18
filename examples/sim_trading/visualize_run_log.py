"""
run_sim.py 运行日志可视化工具
- 解析 .vntrader/log/vt_YYYYMMDD.log
- 可视化 Tick 采样价、双均线、持仓和累计 Tick
- 输出交互式 HTML 文件
"""
import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


DEFAULT_LOG_DIR = Path.home() / ".vntrader" / "log"

LOG_TIME_PATTERN = r"^(?P<log_time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})"
TICK_PATTERN = re.compile(
    LOG_TIME_PATTERN
    + r".*?\[Tick诊断\] 第(?P<count>\d+)个 \| (?P<vt_symbol>[^|]+) \| "
    + r"最新价=(?P<price>-?\d+(?:\.\d+)?) \| 时间=(?P<tick_time>.+)$"
)
STATUS_PATTERN = re.compile(
    LOG_TIME_PATTERN
    + r".*?\[运行中\] 持仓=(?P<pos>-?\d+(?:\.\d+)?), "
    + r"fast_ma=(?P<fast>-?\d+(?:\.\d+)?), "
    + r"slow_ma=(?P<slow>-?\d+(?:\.\d+)?) \| "
    + r"累计Tick=(?P<count>\d+)"
)
ORDER_PATTERN = re.compile(
    LOG_TIME_PATTERN
    + r".*?Send new order -> CTP: OrderRequest\(symbol='(?P<symbol>[^']+)'.*?"
    + r"direction=<Direction\.(?P<direction>[^:]+):.*?"
    + r"volume=(?P<volume>-?\d+(?:\.\d+)?), price=(?P<price>-?\d+(?:\.\d+)?), "
    + r"offset=<Offset\.(?P<offset>[^:]+):.*?reference='(?P<reference>[^']+)'"
)


def parse_datetime(value: str) -> datetime:
    """解析日志中的时间字符串。"""
    value = value.strip()
    if value.endswith("+08:00"):
        value = value[:-6]

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise ValueError(f"无法解析时间: {value}")


def parse_log(log_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """解析 run_sim.py 运行日志。"""
    ticks: list[dict] = []
    statuses: list[dict] = []
    orders: list[dict] = []

    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            tick_match = TICK_PATTERN.search(line)
            if tick_match:
                data = tick_match.groupdict()
                ticks.append(
                    {
                        "log_time": parse_datetime(data["log_time"]),
                        "tick_time": parse_datetime(data["tick_time"]),
                        "vt_symbol": data["vt_symbol"].strip(),
                        "price": float(data["price"]),
                        "tick_count": int(data["count"]),
                    }
                )
                continue

            status_match = STATUS_PATTERN.search(line)
            if status_match:
                data = status_match.groupdict()
                statuses.append(
                    {
                        "log_time": parse_datetime(data["log_time"]),
                        "pos": float(data["pos"]),
                        "fast_ma": float(data["fast"]),
                        "slow_ma": float(data["slow"]),
                        "tick_count": int(data["count"]),
                    }
                )
                continue

            order_match = ORDER_PATTERN.search(line)
            if order_match:
                data = order_match.groupdict()
                orders.append(
                    {
                        "log_time": parse_datetime(data["log_time"]),
                        "symbol": data["symbol"],
                        "direction": data["direction"],
                        "offset": data["offset"],
                        "volume": float(data["volume"]),
                        "price": float(data["price"]),
                        "reference": data["reference"],
                    }
                )

    tick_df = pd.DataFrame(ticks)
    status_df = pd.DataFrame(statuses)
    order_df = pd.DataFrame(orders)

    if not tick_df.empty:
        tick_df.sort_values("tick_time", inplace=True)
    if not status_df.empty:
        status_df.sort_values("log_time", inplace=True)
    if not order_df.empty:
        order_df.sort_values("log_time", inplace=True)

    return tick_df, status_df, order_df


def generate_chart(
    tick_df: pd.DataFrame,
    status_df: pd.DataFrame,
    order_df: pd.DataFrame,
    output_path: Path,
    title: str,
) -> None:
    """生成交互式运行概览图。"""
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.55, 0.2, 0.25],
        subplot_titles=["价格与均线", "持仓", "累计 Tick"],
    )

    if not tick_df.empty:
        fig.add_trace(
            go.Scatter(
                x=tick_df["tick_time"],
                y=tick_df["price"],
                mode="lines+markers",
                name="采样最新价",
                line=dict(width=1.5, color="#00A6D6"),
                marker=dict(size=4),
            ),
            row=1,
            col=1,
        )

    if not order_df.empty:
        colors = order_df["direction"].map({"LONG": "#EF4444", "SHORT": "#22C55E"}).fillna("#FFFFFF")
        text = (
            order_df["direction"]
            + " "
            + order_df["offset"]
            + " @ "
            + order_df["price"].map("{:.1f}".format)
        )
        fig.add_trace(
            go.Scatter(
                x=order_df["log_time"],
                y=order_df["price"],
                mode="markers",
                name="委托",
                marker=dict(size=11, symbol="diamond", color=colors, line=dict(width=1, color="#111827")),
                text=text,
                hovertemplate="%{x}<br>%{text}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    if not status_df.empty:
        fig.add_trace(
            go.Scatter(
                x=status_df["log_time"],
                y=status_df["fast_ma"],
                mode="lines",
                name="fast MA",
                line=dict(width=1.6, color="#F59E0B"),
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=status_df["log_time"],
                y=status_df["slow_ma"],
                mode="lines",
                name="slow MA",
                line=dict(width=1.6, color="#10B981"),
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=status_df["log_time"],
                y=status_df["pos"],
                mode="lines",
                name="持仓",
                line=dict(width=1.8, color="#E11D48", shape="hv"),
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=status_df["log_time"],
                y=status_df["tick_count"],
                mode="lines",
                name="累计 Tick",
                line=dict(width=1.8, color="#6366F1"),
            ),
            row=3,
            col=1,
        )

    fig.update_layout(
        title=dict(text=title, x=0.5),
        template="plotly_dark",
        height=900,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="手数", row=2, col=1)
    fig.update_yaxes(title_text="Tick", row=3, col=1)
    fig.update_xaxes(title_text="时间", row=3, col=1)

    fig.write_html(output_path)


def print_session_summary(tick_df: pd.DataFrame) -> None:
    """打印分时段采样价格摘要。"""
    if tick_df.empty:
        return

    sessions = [
        ("上午", "09:00", "11:30"),
        ("下午", "13:30", "15:00"),
        ("夜盘", "21:00", "23:59"),
    ]

    print("\n分时段采样价格:")
    for name, start_time, end_time in sessions:
        time_text = tick_df["tick_time"].dt.strftime("%H:%M")
        session_df = tick_df[(time_text >= start_time) & (time_text <= end_time)]
        if session_df.empty:
            continue

        print(
            f"  {name}: {len(session_df)} 条 | "
            f"{session_df['tick_time'].iloc[0]} ~ {session_df['tick_time'].iloc[-1]} | "
            f"open={session_df['price'].iloc[0]:.1f}, "
            f"high={session_df['price'].max():.1f}, "
            f"low={session_df['price'].min():.1f}, "
            f"last={session_df['price'].iloc[-1]:.1f}"
        )


def print_signal_summary(status_df: pd.DataFrame, order_df: pd.DataFrame) -> None:
    """打印均线交叉、持仓变化和委托摘要。"""
    if status_df.empty:
        return

    data = status_df.copy()
    data["diff"] = data["fast_ma"] - data["slow_ma"]
    data["sign"] = data["diff"].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))

    non_zero = data[data["sign"] != 0]
    crosses = non_zero[non_zero["sign"].ne(non_zero["sign"].shift())]
    pos_changes = data[data["pos"].ne(data["pos"].shift())]

    print("\n均线状态:")
    print(
        f"  diff范围: {data['diff'].min():+.2f} ~ {data['diff'].max():+.2f} | "
        f"最新diff={data['diff'].iloc[-1]:+.2f}"
    )

    if not crosses.empty:
        print("  交叉/方向变化:")
        for row in crosses.itertuples(index=False):
            direction = "金叉倾向" if row.sign > 0 else "死叉倾向"
            print(
                f"    {row.log_time} | {direction} | "
                f"fast={row.fast_ma:.2f}, slow={row.slow_ma:.2f}, "
                f"pos={row.pos:g}, tick={row.tick_count}"
            )

    if not pos_changes.empty:
        print("\n持仓变化:")
        for row in pos_changes.itertuples(index=False):
            print(
                f"  {row.log_time} | pos={row.pos:g} | "
                f"fast={row.fast_ma:.2f}, slow={row.slow_ma:.2f}, tick={row.tick_count}"
            )

    if not order_df.empty:
        print("\n委托记录:")
        for row in order_df.itertuples(index=False):
            print(
                f"  {row.log_time} | {row.direction} {row.offset} "
                f"{row.volume:g}手 @ {row.price:.1f} | {row.symbol}"
            )


def print_summary(tick_df: pd.DataFrame, status_df: pd.DataFrame, order_df: pd.DataFrame, log_path: Path) -> str:
    """打印并返回图表标题。"""
    vt_symbol = ""
    if not tick_df.empty:
        vt_symbol = str(tick_df["vt_symbol"].iloc[-1])

    starts: list[datetime] = []
    ends: list[datetime] = []
    if not tick_df.empty:
        starts.append(tick_df["tick_time"].iloc[0])
        ends.append(tick_df["tick_time"].iloc[-1])
    if not status_df.empty:
        starts.append(status_df["log_time"].iloc[0])
        ends.append(status_df["log_time"].iloc[-1])

    start = min(starts)
    end = max(ends)

    if not status_df.empty:
        final_pos = status_df["pos"].iloc[-1]
        final_fast = status_df["fast_ma"].iloc[-1]
        final_slow = status_df["slow_ma"].iloc[-1]
        final_ticks = status_df["tick_count"].iloc[-1]
    elif not tick_df.empty:
        final_pos = None
        final_fast = None
        final_slow = None
        final_ticks = tick_df["tick_count"].iloc[-1]
    else:
        raise RuntimeError(f"未从日志中解析到可视化数据: {log_path}")

    print("=" * 72)
    print("run_sim.py 日志摘要")
    print("=" * 72)
    print(f"日志文件: {log_path}")
    if vt_symbol:
        print(f"合约:     {vt_symbol}")
    print(f"时间范围: {start} ~ {end}")
    print(f"价格采样: {len(tick_df)} 条")
    print(f"状态采样: {len(status_df)} 条")
    print(f"委托记录: {len(order_df)} 条")
    print(f"累计Tick: {final_ticks}")

    if final_pos is not None:
        print(f"最终持仓: {final_pos:g}")
        print(f"最终均线: fast={final_fast:.2f}, slow={final_slow:.2f}")

    if not tick_df.empty:
        print(f"采样价格: min={tick_df['price'].min():.1f}, max={tick_df['price'].max():.1f}, last={tick_df['price'].iloc[-1]:.1f}")
    print_session_summary(tick_df)
    print_signal_summary(status_df, order_df)
    print("=" * 72)

    symbol_label = vt_symbol or "run_sim"
    return f"{symbol_label} run_sim 运行概览 ({start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M})"


def main() -> None:
    parser = argparse.ArgumentParser(description="可视化 run_sim.py 运行日志")
    parser.add_argument("--log", type=str, help="日志文件路径，默认按 --date 从 .vntrader/log 读取")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y%m%d"), help="日志日期，如 20260415")
    parser.add_argument("--output", type=str, default="run_sim_report.html", help="输出 HTML 路径")
    args = parser.parse_args()

    log_path = Path(args.log) if args.log else DEFAULT_LOG_DIR / f"vt_{args.date}.log"
    output_path = Path(args.output)

    tick_df, status_df, order_df = parse_log(log_path)
    title = print_summary(tick_df, status_df, order_df, log_path)
    generate_chart(tick_df, status_df, order_df, output_path, title)

    print(f"图表已生成: {output_path.resolve()}")


if __name__ == "__main__":
    main()
