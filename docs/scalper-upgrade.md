# Scalper safety and strategy update

## Manual entry assistant

### Direct connection on Windows

The terminal now defaults to the experimental `--strategy adaptive`
(`adaptive_trend_breakout_v1`). Use `--strategy pullback` to retain the previous
`m1_pullback_breakout_v1` rules. The adaptive candidate adds M5 ADX/slope/EMA
separation and anti-chasing filters, then selects the existing pullback or a
closed 20-bar breakout confirmed by broker tick volume. It tightens the spread
budget to 0.1 ATR and candle-range ceiling to 2.5 ATR. These are unoptimized
engineering choices, not evidence of improved returns. Exit logic remains
ATR/swing SL and a fixed reward/risk target. See the Vietnamese usage guide
for exact rules. Logs identify the strategy and setup; Kelly histories are
filtered by the selected strategy ID and never pooled across versions.

The terminal view uses green for BUY/TP, red for SELL/SL, yellow for WAIT and
warnings, and cyan for entry prices. It shows one preferred direction, a
price/lot/risk/margin table, M15/M5 trend context and M1 RSI/ADX/ATR, and Kelly
data status. The indicator table is context, not a calibrated confidence score.
Snapshot/expiry times are displayed in UTC+7; JSON timestamps remain UTC.
Press `c` to clear the terminal, `h` for help, or `q` to exit; none of these
fetch prices. Enter alone fetches a new snapshot. Color is detected from the
terminal; use `--color always` to force it or `--color never` for plain output.

With the Windows MT5 terminal logged in, use the read-only Python connection
to avoid depending on an EA remaining attached to a chart:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py
```

This requires `MetaTrader5` and `TA-Lib` in the Python environment. The bot
waits in the terminal. Press Enter to fetch 5,000 closed M1 candles, current
bid/ask, broker specifications and equity, then analyze once. Press Enter
again for a new analysis, or type `q` to exit. There is no background polling.
By default results appear only in the terminal; `--output logs/entry_plan.json`
optionally saves a snapshot. `--once` analyzes once immediately and exits.

For a valid BUY setup, the conditional entry is above both current ask and
the last closed candle high adjusted for spread, rounded up to a tick. The
SELL equivalent is below bid and the last closed candle low, rounded down.
Stops come from the strategy and targets are recalculated at the entry price
using its reward/risk ratio. BUY targets mean sell to close; SELL targets mean
buy to close, not open a reversal position. These are conditional scenarios,
not guaranteed predictions of future prices. Without a valid setup, the bot
reports WAIT. Stale quotes and connection errors produce BLOCKED. At zero
equity, price analysis remains available with no lot recommendation.

Use `--symbol` and `--risk-percent` to configure the symbol and sizing budget.
Plans expire after at most 15 seconds; press Enter again to recheck current
conditions. The assistant sends no trade requests. Broker stop/freeze distance,
margin, position exposure and transaction costs require separate review.

### Kelly lot sizing

When the strategy reports WAIT with valid data but no entry setup, the terminal
shows at most one preferred BUY or SELL reference scenario with entry/SL/TP.
BUY requires M15 close above EMA200 and M5 EMA9 above EMA21; SELL requires
both reversed. Conflicting or equal readings show WAIT without a scenario.
This directional preference does not claim a calibrated win probability.
The scenario's lot sizes
are hypothetical fixed-risk calculations at the configured risk ceiling,
clearly labeled as **not Kelly** and **not entry recommendations**. Kelly
history from confirmed setups does not establish an edge for these scenarios.
Zero equity or failed broker calculations show `Lot: N/A` while preserving
the reference prices. Invalid-data safety rejections do not create scenarios.
Spread/range rejections can show directional reference prices but always
suppress their lot. Press Enter again to recheck; WAIT remains the recommendation.

The terminal assistant now defaults to `--sizing kelly`. It still waits for
Enter and does not run in the background. Price analysis remains available
without enough Kelly history, but **no fixed-risk lot is silently substituted**.
For the previous fixed budget, explicitly use `--sizing fixed`.

Create `logs/kelly_history.csv` using the header in
`docs/examples/kelly_history_template.csv`. Each row must represent one fully closed
trade from the selected strategy, not an individual
fill or a partially closed position. Required columns:

| Column | Value |
| --- | --- |
| `trade_id` | Unique identifier for the complete trade |
| `closed_at_utc` | Timezone-aware ISO close time, e.g. `2026-10-28T08:00:00Z` |
| `symbol` | Exact broker symbol, e.g. `XAUUSDc` |
| `strategy_id` | `adaptive_trend_breakout_v1`, or `m1_pullback_breakout_v1` with `--strategy pullback` |
| `net_r` | Net realized P&L / initial planned cash loss at SL |

Net P&L must include all entry/exit commissions, fees, swaps and partial fills.
For example, net profit 20 on initial cash risk 10 is `2`; net loss 12 on
initial risk 10 is `-1.2`. These numbers illustrate the format, not observed
performance. Do not mix other strategies, historical scalper entries at market,
or incompatible strategy versions into this sample. The assistant cannot
automatically infer the strategy of manually entered MT5 trades.

By default it uses the latest 200 matching trades closed within 180 days and
requires at least 50. Duplicated IDs, future/naive timestamps and nonfinite
results invalidate the input. Both wins and losses must be present. Breakeven
trades remain in the probability denominator, conservatively treated as
non-wins. The standard binary-outcome Kelly approximation is
`f = p - (1-p)/b`, where `b` is average positive net R / average absolute
negative net R. Actual variable outcomes need not fit this two-outcome model.

The sizing estimate substitutes the 95% Wilson lower bound on win probability,
caps the historical payoff ratio by the current scenario's gross reward/risk,
then multiplies positive Kelly by 0.25. Risk is capped at 0.5% equity by default.
Wilson protects only the win-probability estimate under its assumptions; it
does not establish a confidence bound on profitability or guarantee safety.
No positive conservative edge means no lot recommendation. The fixed strategy
score 0.6 is never used as a win probability.

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --kelly-history logs/kelly_history.csv --kelly-fraction 0.25 --risk-percent 0.5
```

`--risk-percent` is a ceiling, not a promise to risk that amount. The CLI allows
at most 5%; the default remains 0.5%. `--min-trades` accepts 30–200; default 50.
`--cost-per-lot` supplies estimated round-trip fees in **account currency**,
default 0 (fees are not automatically detected). `--slippage-ticks` defaults
to 2 adverse ticks at both entry and stop. For cent accounts, all monetary
inputs and outputs use the account currency, e.g. USC, rather than USD.

Lot estimates use MT5 `order_calc_profit` for the adverse entry/stop and round
down to the broker's volume step. Minimum lots are never rounded up. Margin
estimates use `order_calc_margin`, constrain the new trade to at most half of
current free margin, and recheck the final volume. API errors suppress lots.
Entry/SL/TP are rounded to tick size and conditional entries respect broker
minimum stop distances. These are local estimates, not broker order approval.
The direct terminal assistant now aggregates gross further stop risk across
open positions and pending limit/stop orders, with a default 2% equity cap
(`--max-total-risk`). Missing SLs, unsupported stop-limit orders and read errors
suppress new lots. Broker directional volume limits are also checked. Existing
exposure estimates exclude fees, slippage and gaps. Margin calculation does
not account for all position interactions. Gap losses can exceed
the budget. Estimated risk excludes unprovided fees and overnight financing.

References: [Kelly trade-history estimation](https://www.quantconnect.com/research/18312/kelly-criterion-applications-in-trading-systems/p1),
[MT5 profit calculation](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py),
[MT5 margin calculation](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py).

### CSV bridge connection

Compile the updated `bridge/MT5_Data_Bridge.mq5` in MetaEditor and attach it
to a chart. It exports candles and a separate live quote CSV, including the
broker's tick value for losses and volume limits. No orders are submitted.

On Windows, the runner defaults to `%APPDATA%/MetaQuotes/Terminal/Common/Files`.
Use the actual broker symbol and current account equity:

```powershell
python run_scalper.py --symbol XAUUSDc --equity 10000 --risk-percent 0.5
```

For another directory, pass `--csv "C:/path/MT5_XAUUSDc_M1.csv"` and optionally
`--quote "C:/path/MT5_XAUUSDc_quote.csv"`. Without `--equity`, the runner
continues generating signals without position sizing.

`logs/entry_plan.json` reports WAIT, BLOCKED, or REVIEW. REVIEW includes the
current BUY ask / SELL bid, strategy SL/TP, actual reward/risk, volume rounded
down to the broker step, and estimated loss in account currency. The minimum
reward/risk is 1.5. Insufficient budget for the minimum lot blocks the plan.
Quotes older than 15 seconds or with a different symbol are rejected. Plans
are refreshed every poll, even within the same candle; check their expiration
before manual entry. The next poll clears the preceding plan before validating
new data. Consumers must reject expired plans if the process stops.

Equity is supplied manually: restart with an updated value when it changes.
Sizing estimates stop loss only; commission, slippage, gaps, margin and existing
account exposure are not included. Validate broker timestamps against UTC;
incorrect or future timestamps block assistance. The fixed confidence score
is not a win probability. This feature has not been validated for profitability.

The M1 scalper remains signal-only. Run it with `python run_scalper.py` using
its configured MT5 CSV path. Existing AI modes continue to use `main.py`.

Data preparation rejects nonfinite prices, impossible OHLC bars, negative
volume and timestamps that are not minute openings. It excludes forming M1
candles and incomplete M5/M15 groups. Prediction blocks recent gaps and stale
or future higher-timeframe context when timestamp indexes are supplied.
Callers should always use `prepare_scalping_data` to supply UTC indexes.

The strategy retains M1 EMA21 pullbacks with M5 momentum and M15 EMA200 trend.
It now excludes RSI extremes (BUY >=75, SELL <=25) and candles wider than
3 ATR. Stops use the wider of 1.5 ATR and a five-bar swing plus 0.1 ATR;
targets remain twice the resulting stop distance. Wider stops require smaller
positions in any future execution integration.

`predict(..., spread=ask-bid)` optionally blocks spread above 0.15 ATR.
Spread must be in price units. The CSV runner activates this check when
entry assistance is enabled with `--equity`. Confidence 0.6
is a fixed strategy score, not a calibrated probability of profit.

In the AI entrypoint, reduced capital allocations now reduce lot size,
combined with the macro multiplier. Scaling rounds down to the existing
0.01 lot precision. Broker-specific volume steps still require execution
validation. Invalid ATR, direction and risk multipliers fail before allocation.
The missing NumPy import in sequence construction has also been fixed.

Validation uses deterministic regression tests, not evidence of profitability.
Before live use, evaluate on unseen broker history with spread, commission,
slippage and gap fills, then run on a demo account. No live orders were sent
as part of this update.
