"""Entry point for the XAU US Session Breakout Playbook (Submission version)."""
import math
from typing import Any
from getagent import backtest, data, runtime


def _sanitize(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _sanitize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize(val) for key, val in metrics.items()}


def run() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    symbols = cfg.get("trading_symbols") or ["XAUUSDT"]
    symbol = symbols[0]

    bars = data.crypto.futures.kline(
        symbol=symbol,
        interval="1h",
        limit=1000,
    )
    replay_frame = backtest.prepare_frame(bars, datetime_index="date")

    if replay_frame.empty:
        runtime.emit_signal(action="watch", symbol=symbol, confidence=0.0,
            metrics={"rows": 0}, meta={"reason": "no historical bars returned"})
        return

    instrument_key = f"{symbol}.BINANCE"
    result = backtest.run(ohlcv_data={instrument_key: replay_frame}, spec=runtime.backtest_spec)
    chart_path = backtest.generate_chart(result)

    summary = result.summary or {}
    net_pnl_raw = summary.get("net_pnl", 0)
    try:
        net_pnl = float(net_pnl_raw or 0)
    except (TypeError, ValueError):
        net_pnl = 0.0

    action = "long" if net_pnl > 0 else "watch"
    metrics = _sanitize_metrics({
        "total_return_pct": result.total_return_pct,
        "net_pnl": net_pnl,
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown_pct": result.max_drawdown_pct,
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "profit_factor": result.profit_factor,
    })

    runtime.emit_signal(action=action, symbol=symbol,
        confidence=_sanitize(result.win_rate) or 0.0,
        metrics=metrics, meta={"chart_path": chart_path})


if __name__ == "__main__":
 