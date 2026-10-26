# Scalper safety and strategy update

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
Spread must be in price units. The CSV runner has no bid/ask quote source,
so this check is only active when the caller provides spread. Confidence 0.6
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
