"""XAU US Session Breakout Strategy — NautilusTrader implementation.

Strategy logic:
1. Track London (07:00-13:00 UTC) and US (13:00-20:00 UTC) trading sessions
2. Track the highest high and lowest low of each session
3. After a session closes, its high/low become reference levels
4. Breakout above prior session high → Long entry
5. Breakout below prior session low → Short entry
6. Initial stop loss = 25% of current day's range (daily high-low)
7. Take profit = stop distance × 2 (1:2 risk-reward)
8. Trailing stop: for every 1% profit, stop advances by 1% from entry
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class XauSessionBreakoutConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    trade_size: str = "0.1"
    stop_atr_multiple: float = 0.25
    rr_target: float = 2.0
    trailing_step: float = 0.01


class TradingSession:
    def __init__(self, name: str, start_hour: int, end_hour: int):
        self.name = name
        self.start_hour = start_hour
        self.end_hour = end_hour

    def is_active(self, hour: int) -> bool:
        return self.start_hour <= hour < self.end_hour


class XauSessionBreakoutStrategy(Strategy):
    SESSIONS = [
        TradingSession("LONDON", 7, 13),
        TradingSession("US", 13, 20),
    ]

    def __init__(self, config: XauSessionBreakoutConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._current_levels: dict = {}
        self._in_session: dict = {}
        self._prior_levels: dict = {}
        self._ready_sessions: set = set()
        for s in self.SESSIONS:
            self._current_levels[s.name] = {"high": None, "low": None}
            self._in_session[s.name] = False
            self._prior_levels[s.name] = {"high": None, "low": None}
        self._day_high: Optional[float] = None
        self._day_low: Optional[float] = None
        self._current_day: Optional[int] = None
        self._position_side: str = "NONE"
        self._entry_price: Optional[float] = None
        self._stop_price: Optional[float] = None
        self._take_profit_price: Optional[float] = None
        self._highest_price_since_entry: Optional[float] = None
        self._lowest_price_since_entry: Optional[float] = None
        self._instrument: Optional[Instrument] = None

    def on_start(self) -> None:
        bt = self.cfg.bar_type or (self.cfg.bar_types[0] if self.cfg.bar_types else None)
        iid = self.cfg.instrument_id or (self.cfg.instrument_ids[0] if self.cfg.instrument_ids else None)
        if bt is None or iid is None:
            raise RuntimeError("bar_type and instrument_id must be set")
        self._instrument = self.cache.instrument(iid)
        self.subscribe_bars(bt)

    def on_bar(self, bar: Bar) -> None:
        ts_dt = datetime.fromtimestamp(bar.ts_event / 1_000_000_000, tz=timezone.utc)
        bar_hour = ts_dt.hour
        bar_day = ts_dt.day
        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)

        if self._current_day != bar_day:
            self._current_day = bar_day
            self._day_high = high
            self._day_low = low
        else:
            if self._day_high is not None:
                self._day_high = max(self._day_high, high)
            if self._day_low is not None:
                self._day_low = min(self._day_low, low)

        for session in self.SESSIONS:
            name = session.name
            active = session.is_active(bar_hour)
            was_active = self._in_session.get(name, False)

            if active and not was_active:
                self._current_levels[name] = {"high": None, "low": None}

            if active:
                self._in_session[name] = True
                cur = self._current_levels[name]
                cur["high"] = max(cur["high"], high) if cur["high"] is not None else high
                cur["low"] = min(cur["low"], low) if cur["low"] is not None else low

            if not active and was_active:
                self._in_session[name] = False
                ended = self._current_levels[name]
                if ended["high"] is not None and ended["low"] is not None:
                    self._prior_levels[name] = {"high": ended["high"], "low": ended["low"]}
                    self._ready_sessions.add(name)

        if self._position_side != "NONE":
            self._manage_position(high, low, close)
        else:
            self._check_entries(high, low, close)

    def _check_entries(self, high: float, low: float, close: float) -> None:
        if not self._ready_sessions or self._day_high is None or self._day_low is None:
            return
        day_range = self._day_high - self._day_low
        if day_range <= 0:
            return

        stop_distance = day_range * self.cfg.stop_atr_multiple
        instrument = self._instrument
        if instrument is None:
            return

        qty = Quantity(Decimal(str(self.cfg.trade_size)), instrument.size_precision)

        for session in self.SESSIONS:
            name = session.name
            if name not in self._ready_sessions:
                continue
            prior = self._prior_levels.get(name, {})
            ph = prior.get("high")
            pl = prior.get("low")
            if ph is None or pl is None:
                continue

            if high > ph and close > ph:
                entry_price_val = max(close, ph * 1.0005)
                stop_price_val = entry_price_val - stop_distance
                if stop_price_val < entry_price_val:
                    tp = entry_price_val + (stop_distance * self.cfg.rr_target)
                    self._enter_long(instrument.id, qty, entry_price_val, stop_price_val, tp)
                    return

            if low < pl and close < pl:
                entry_price_val = min(close, pl * 0.9995)
                stop_price_val = entry_price_val + stop_distance
                if stop_price_val > entry_price_val:
                    tp = entry_price_val - (stop_distance * self.cfg.rr_target)
                    self._enter_short(instrument.id, qty, entry_price_val, stop_price_val, tp)
                    return

    def _enter_long(self, iid, qty, entry, sl, tp):
        self._position_side = "LONG"
        self._entry_price = entry
        self._stop_price = sl
        self._take_profit_price = tp
        self._highest_price_since_entry = entry
        o = self.order_factory.market(iid, OrderSide.BUY, qty, TimeInForce.GTC)
        self.submit_order(o)

    def _enter_short(self, iid, qty, entry, sl, tp):
        self._position_side = "SHORT"
        self._entry_price = entry
        self._stop_price = sl
        self._take_profit_price = tp
        self._lowest_price_since_entry = entry
        o = self.order_factory.market(iid, OrderSide.SELL, qty, TimeInForce.GTC)
        self.submit_order(o)

    def _manage_position(self, high, low, close):
        if self._entry_price is None or self._stop_price is None:
            return
        if self._position_side == "LONG":
            if self._highest_price_since_entry is None or high > self._highest_price_since_entry:
                self._highest_price_since_entry = high
            self._update_trailing_stop_long()
            if low <= self._stop_price:
                self._exit_position("SL", low); return
            if self._take_profit_price is not None and high >= self._take_profit_price:
                self._exit_position("TP", high); return
        elif self._position_side == "SHORT":
            if self._lowest_price_since_entry is None or low < self._lowest_price_since_entry:
                self._lowest_price_since_entry = low
            self._update_trailing_stop_short()
            if high >= self._stop_price:
                self._exit_position("SL", high); return
            if self._take_profit_price is not None and low <= self._take_profit_price:
                self._exit_position("TP", low); return

    def _update_trailing_stop_long(self):
        if None in (self._entry_price, self._highest_price_since_entry):
            return
        pct = (self._highest_price_since_entry - self._entry_price) / self._entry_price
        if pct >= self.cfg.trailing_step:
            steps = int(pct / self.cfg.trailing_step)
            if steps >= 1:
                ns = self._entry_price * (1.0 + (steps - 1) * self.cfg.trailing_step)
                if self._stop_price is not None and ns > self._stop_price:
                    self._stop_price = ns

    def _update_trailing_stop_short(self):
        if None in (self._entry_price, self._lowest_price_since_entry):
            return
        pct = (self._entry_price - self._lowest_price_since_entry) / self._entry_price
        if pct >= self.cfg.trailing_step:
            steps = int(pct / self.cfg.trailing_step)
            if steps >= 1:
                ns = self._entry_price * (1.0 - (steps - 1) * self.cfg.trailing_step)
                if self._stop_price is not None and ns < self._stop_price:
                    self._stop_price = ns

    def _exit_position(self, reason, price):
        inst = self._instrument
        if inst is None:
            return
        side = OrderSide.SELL if self._position_side == "LONG" else OrderSide.BUY
        for p in self.cache.positions_open(instrument_id=inst.id):
            o = self.order_factory.market(inst.id, side, p.quantity, TimeInForce.GTC)
            self.submit_order(o)
        self._position_side = "NONE"

    def on_stop(self) -> None:
        if self._instrument is not None:
            self.cancel_all_orders(self._instrument.id)
            self.close_all_positions(self._instrument.id)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             