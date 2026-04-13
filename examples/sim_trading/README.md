# SimNow 仿真交易 - 快速启动指南

## 环境状态

| 组件 | 版本 | 状态 |
|------|------|------|
| Python | 3.10.13 | ✅ |
| vnpy | 4.3.0 | ✅ |
| vnpy_ctp | 6.7.11.4 | ✅ |
| vnpy_ctastrategy | 1.4.1 | ✅ |
| vnpy_sqlite | 1.1.3 | ✅ |

## 文件说明

| 文件 | 说明 |
|------|------|
| `run_backtest.py` | **本地回测脚本**（推荐先运行），自动生成模拟数据并回测双均线策略，无需外部连接 |
| `run_sim.py` | **SimNow 实盘仿真脚本**，连接 SimNow CTP 仿真服务器进行实时模拟交易 |
| `run_recorder.py` | **独立行情录制**，持续录制 Tick 行情并合成 1 分钟 K 线存入数据库 |
| `visualize_data.py` | **数据可视化工具**，将数据库中已录制的 K 线数据生成交互式图表（HTML） |

> ⚠️ 当前服务器网络无法直接访问 SimNow 服务器（180.168.146.187），`run_sim.py` 需要在可联网的本地电脑上运行。`run_backtest.py` 可在当前环境直接运行。

## 快速开始（本地回测）

```bash
cd /home/jinuo.cy/vnpy/examples/sim_trading
python3 run_backtest.py
```

## SimNow 实盘仿真

### 第一步：填写 SimNow 账号

编辑 `run_sim.py`，在 `CTP_SETTING` 中填入你的 SimNow 账号信息：

```python
CTP_SETTING = {
    "用户名": "你的SimNow账号",    # 手机号
    "密码": "你的SimNow密码",
    ...
}
```

> 如果没有 SimNow 账号，请前往 https://www.simnow.com.cn/ 注册

### 第二步：确认合约代码

脚本默认交易 **螺纹钢 rb2610.SHFE**，请根据当前主力合约调整：

```python
STRATEGY_CONFIG = {
    "vt_symbol": "rb2610.SHFE",   # 修改为当前主力合约
    ...
}
```

### 第三步：启动模拟交易

```bash
cd /home/jinuo.cy/vnpy/examples/sim_trading
python3 run_sim.py
```

### 第四步：停止交易

按 `Ctrl+C` 安全停止。

## SimNow 服务器说明

脚本默认使用 **第二套环境**（7x24h 可用，适合测试）：

| 环境 | 交易服务器 | 行情服务器 | 可用时间 |
|------|-----------|-----------|---------|
| 第一套 | 180.168.146.187:10201 | 180.168.146.187:10211 | 交易时段 |
| **第二套** | **180.168.146.187:10202** | **180.168.146.187:10212** | **7x24h** |

> 注意：第二套环境行情数据为模拟回放，非实时行情；第一套为实时行情但仅交易时段可用。

## 策略说明

**双均线策略（DoubleMaStrategy）**：
- **快速均线**：10 周期 SMA
- **慢速均线**：20 周期 SMA
- **做多信号**：快线上穿慢线（金叉）
- **做空信号**：快线下穿慢线（死叉）
- **仓位管理**：每次交易 1 手

## 常见问题

### Q: 连接失败怎么办？
- 确认 SimNow 账号密码正确
- 确认网络可以访问 180.168.146.187
- SimNow 每天 16:00-17:00 为结算时间，此时段无法连接

### Q: 如何修改策略参数？
修改 `STRATEGY_CONFIG["setting"]` 中的参数：
```python
"setting": {
    "fast_window": 5,    # 更短的快速均线
    "slow_window": 30,   # 更长的慢速均线
}
```

### Q: 如何切换其他内置策略？
vnpy_ctastrategy 内置了多种策略，修改 `class_name` 即可：
- `DoubleMaStrategy` - 双均线策略
- `BollChannelStrategy` - 布林通道策略
- `AtrRsiStrategy` - ATR-RSI 策略
- `KingKeltnerStrategy` - 肯特纳通道策略
- `DualThrustStrategy` - Dual Thrust 策略
- `TurtleSignalStrategy` - 海龟信号策略
