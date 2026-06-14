# XAU US Session Breakout — 黄金美盘突破交易策略

## 策略概述

本策略基于 **XAUUSDT 永续合约**的保守型突破交易策略。核心思路是**以上一个美盘交易时间（US Session 13:30-20:00 UTC）的最高价和最低价为关键参考位，突破高点做多，跌破低点做空**。一年回测（2025.05-2026.05）：夏普比率 3.01，盈亏比 3.21，胜率 50%，最大回撤 < 2%，共 16 笔交易。

A conservative breakout trading strategy on XAUTUSDT (Tether Gold) that uses the prior US trading session's high and low as key institutional reference levels.

## Strategy Overview

## 策略（Strategy）

Price captures directional moves triggered by breakouts from the previous US trading session's price range. The US session (13:30–20:00 UTC, covering the overlap of London and New York markets) establishes the most significant intraday support and resistance levels. Breakouts from these levels during Asian or European hours often lead to sustained runs.

### 开仓（Entry）

Based on prior US session high/low breakouts:
- **做多（Long）**: When price breaks above the prior US session high with confirmation
- **做空（Short）**: When price breaks below the prior US session low with confirmation

### 平仓（Exit）

Three exit mechanisms:
1. **止损（Stop Loss）**: Initial stop at 40% of daily range from entry
2. **止盈（Take Profit）**: Fixed 1:2 risk-reward ratio from entry
3. **移动止损（Trailing Stop）**: Every 1% profit advances stop by 1% from entry

### 风险（Risk）

- Conservative position sizing with layered risk management
- Underperforms in low-volatility, choppy markets where breakouts fail
- Whipsaw risk around major economic events (NFP, FOMC)
- Gold is sensitive to USD strength, real yields, and geopolitical events

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `stop_atr_multiple` | 0.40 | Stop loss as fraction of current day's range |
| `rr_target` | 2.0 | Risk-reward ratio (take profit = stop × this value) |
| `trailing_step` | 0.01 | Trailing stop step (1% = 0.01) |
| `margin_budget` | 1000 | Per-strategy capital cap |

### Risk Considerations

- Underperforms in low-volatility, choppy markets where breakouts fail
- Whipsaw risk around major economic events (NFP, FOMC)
- Gold is sensitive to USD strength, real yields, and geopolitical events
- Past backtest performance is not a guarantee of live profitability

## Files

```
xau-session-breakout/
├── README.md
├── manifest.yaml          # Package metadata & config
├── backtest.yaml          # Nautilus backtest spec
├── src/
│   ├── main.py            # Entry point: data fetch → backtest → emit signal
│   └── strategy.py        # Strategy logic: session tracking, entries, risk
```

## Usage

1. Package and upload:
```bash
tar czf xau-session-breakout.tar.gz .
curl -X POST -H "ACCESS-KEY: <your_key>" -F "package=@xau-session-breakout.tar.gz" https://api.bitget.com/api/v1/playbook/upload
```

2. Run backtest:
```bash
curl -X POST -H "ACCESS-KEY: <your_key>" -H "Content-Type: application/json" -d '{"version_id": "<draft_id>"}' https://api.bitget.com/api/v1/playbook/run
```
