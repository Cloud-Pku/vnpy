"""
RSI高频交易策略 - 产生更频繁的交易信号
- 使用RSI指标判断超买超卖
- 缩短周期，增加交易频率
- 适合快速验证监控功能
"""
import numpy as np
import sqlite3
from pathlib import Path
from datetime import datetime

from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)

# 数据库路径
DB_PATH = Path("C:/Users/Lenovo/.vntrader/database.db")


def save_trade_to_db(strategy_name: str, symbol: str, exchange: str, 
                     action: str, direction: str, offset: str,
                     price: float, volume: int, pos_after: int):
    """保存交易记录到数据库"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        now = datetime.now()
        trade_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
        trade_date = now.strftime("%Y%m%d")
        
        cursor.execute('''
            INSERT INTO trade_records 
            (strategy_name, symbol, exchange, action, direction, offset,
             price, volume, pos_after, trade_datetime, trade_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (strategy_name, symbol, exchange, action, direction, offset,
              price, volume, pos_after, trade_datetime, trade_date))
        
        conn.commit()
        conn.close()
    except Exception as e:
        # 记录错误但不影响策略运行
        print(f"[ERROR] 保存交易记录失败: {e}")


class RsiStrategy(CtaTemplate):
    """
    RSI高频交易策略
    """
    
    author = "高频交易测试"
    
    # 策略参数（短周期，频繁交易）
    rsi_window: int = 7          # RSI周期（短）
    rsi_overbought: float = 65   # 超买线（较低）
    rsi_oversold: float = 35     # 超卖线（较高）
    
    # 策略变量
    rsi_value: float = 50.0
    
    parameters = ["rsi_window", "rsi_overbought", "rsi_oversold"]
    variables = ["rsi_value"]
    
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=50)  # 减小缓冲区，更快启动
        self.last_tick: TickData = None  # 保存最新Tick用于K线记录
    
    def on_init(self):
        """策略初始化"""
        self.write_log(f"[{self.strategy_name}] RSI策略初始化，周期={self.rsi_window}")
        self.load_bar(3)  # 只加载3天数据，更快启动
    
    def on_start(self):
        """策略启动 - 检查持仓同步状态"""
        # 尝试从CTP获取实际持仓
        try:
            parts = self.vt_symbol.split('.')
            if len(parts) == 2:
                sym, exch = parts
                long_posid = f"{sym}.{exch}.Long"
                short_posid = f"{sym}.{exch}.Short"
                
                long_pos_data = self.cta_engine.main_engine.get_position(long_posid)
                short_pos_data = self.cta_engine.main_engine.get_position(short_posid)
                
                long_vol = long_pos_data.volume if long_pos_data else 0
                short_vol = short_pos_data.volume if short_pos_data else 0
                actual_pos = long_vol - short_vol
                
                if self.pos != actual_pos:
                    self.write_log(
                        f"[{self.strategy_name}] ⚠️ 持仓不一致! "
                        f"策略持仓={self.pos}, 实际持仓={actual_pos} "
                        f"(多={long_vol}, 空={short_vol})"
                    )
                    # 强制同步持仓
                    old_pos = self.pos
                    self.pos = actual_pos
                    self.write_log(
                        f"[{self.strategy_name}] 🔄 已强制同步持仓: {old_pos} → {actual_pos}"
                    )
                else:
                    self.write_log(f"[{self.strategy_name}] ✅ 持仓已同步: {self.pos}")
            else:
                self.write_log(f"[{self.strategy_name}] 策略持仓={self.pos}")
        except Exception as e:
            self.write_log(f"[{self.strategy_name}] 检查持仓失败: {e}")
        
        self.write_log(f"[{self.strategy_name}] RSI策略启动，准备高频交易！")
        self.put_event()
    
    def on_stop(self):
        """策略停止"""
        self.write_log(f"[{self.strategy_name}] RSI策略停止")
        self.put_event()
    
    def on_tick(self, tick: TickData):
        """Tick数据回调"""
        self.last_tick = tick  # 保存最新Tick
        self.bg.update_tick(tick)
    
    def on_bar(self, bar: BarData):
        """K线数据回调 - 核心交易逻辑"""
        self.cancel_all()
        
        # 夜盘开盘前5分钟（21:00-21:05）不交易，避免跳空波动
        bar_time = bar.datetime.time()
        if bar_time.hour == 21 and bar_time.minute < 5:
            return
        
        am = self.am
        am.update_bar(bar)
        
        if not am.inited:
            self.write_log(f"[{self.strategy_name}] 预热中... {am.count}/{self.rsi_window+5}")
            return
        
        # 计算RSI
        self.rsi_value = am.rsi(self.rsi_window)
        
        # 高频交易逻辑
        # 注意：需要考虑已有委托未成交的情况，避免重复下单导致仓位异常
        if self.rsi_value < self.rsi_oversold:
            # 超卖 - 买入信号
            # 只有空仓或无仓位时才买
            if self.pos < 0:
                # 有空仓，先平空
                self.cover(bar.close_price, abs(self.pos))
                self.write_log(f"[{self.strategy_name}] RSI={self.rsi_value:.1f} 超卖平仓，准备买入")
            elif self.pos == 0:
                # 无持仓，开多
                self.buy(bar.close_price, 1)
                self.write_log(f"[{self.strategy_name}] 🟢 RSI={self.rsi_value:.1f} 买入信号 @ {bar.close_price}")
        
        elif self.rsi_value > self.rsi_overbought:
            # 超买 - 卖出信号
            # 只有多仓或无仓位时才卖
            if self.pos > 0:
                # 有多仓，先平多
                self.sell(bar.close_price, abs(self.pos))
                self.write_log(f"[{self.strategy_name}] RSI={self.rsi_value:.1f} 超买平仓，准备卖出")
            elif self.pos == 0:
                # 无持仓，开空
                self.short(bar.close_price, 1)
                self.write_log(f"[{self.strategy_name}] 🔴 RSI={self.rsi_value:.1f} 卖出信号 @ {bar.close_price}")
        
        # 每5根K线输出一次状态（用于监控）
        if am.count % 5 == 0:
            self.write_log(f"[{self.strategy_name}] [运行中] RSI={self.rsi_value:.1f} 持仓={self.pos} 价格={bar.close_price}")
        
        self.put_event()
    
    def on_trade(self, trade: TradeData):
        """成交回调 - 关键：输出交易信息到日志供监控解析，并入库"""
        # 使用英文枚举值判断 (Direction.LONG.value="Long", Offset.OPEN.value="Open")
        dir_val = trade.direction.value      # "Long" or "Short"
        off_val = trade.offset.value         # "Open", "Close", "Close Today"
            
        # 日志输出中文描述
        action_cn = "买入" if dir_val == "Long" else "卖出"
        # "Open" -> 开仓, "Close"/"Close Today" -> 平仓
        offset_cn = "开仓" if off_val == "Open" else "平仓"
            
        self.write_log(
            f"[{self.strategy_name}] [成交] {action_cn}{offset_cn} "
            f"价格={trade.price} 数量={trade.volume} "
            f"持仓={self.pos}"
        )
    
        # 确定action类型 (BUY, SELL, SHORT, COVER)
        if dir_val == "Long":
            trade_action = "BUY" if off_val == "Open" else "COVER"
        else:  # Short
            trade_action = "SHORT" if off_val == "Open" else "SELL"
    
        # 保存到数据库
        save_trade_to_db(
            strategy_name=self.strategy_name,
            symbol=trade.symbol,
            exchange=trade.exchange.value,
            action=trade_action,
            direction=dir_val,
            offset=off_val,
            price=trade.price,
            volume=trade.volume,
            pos_after=self.pos
        )
    
        self.put_event()
    
    def on_order(self, order: OrderData):
        """委托回调 - 处理委托状态变化"""
        # 委托被拒绝时记录日志（可能是持仓不足、资金不足等）
        if order.status.name == "REJECTED":
            self.write_log(
                f"[{self.strategy_name}] ⚠️ 委托被拒绝: {order.vt_symbol} "
                f"{order.direction.value} {order.offset.value} "
                f"价格={order.price} 数量={order.volume} "
                f"当前持仓={self.pos}"
            )
    
    def on_stop_order(self, stop_order: StopOrder):
        """停止单回调"""
        pass
    