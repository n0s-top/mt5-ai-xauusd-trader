from pathlib import Path
import pandas as pd

COMMON = (
    Path.home()
    / ".var/app/com.usebottles.bottles/data/bottles/bottles/"
      "MetaTrader5/drive_c/users/han/AppData/Roaming/"
      "MetaQuotes/Terminal/Common/Files"
)

prices = pd.read_csv(
    COMMON / "MT5_XAUUSDc_M1.csv",
    encoding="utf-16",
)

prices["time"] = pd.to_datetime(
    prices["time"], unit="s", utc=True
)

prices = prices.sort_values("time").reset_index(drop=True)

signals = pd.read_csv("backtests/xauusdc_signals.csv")
signals["time"] = pd.to_datetime(signals["time"], utc=True)
signals = signals[signals["direction"] != 0].copy()

MAX_HOLD_BARS = 120
MAX_GAP_SECONDS = 90

results = []
busy_until = pd.Timestamp.min.tz_localize("UTC")

for _, signal in signals.iterrows():
    entry_time = signal["time"]

    if entry_time <= busy_until:
        continue

    future = prices[prices["time"] >= entry_time]

    if future.empty:
        continue

    entry_bar = future.iloc[0]

    # Only enter at the next expected M1 opening.
    if entry_bar["time"] != entry_time:
        continue

    direction = int(signal["direction"])
    entry = float(entry_bar["open"])
    sl = float(signal["stop_loss"])
    tp = float(signal["take_profit"])

    if direction == 1 and not (sl < entry < tp):
        continue

    if direction == -1 and not (tp < entry < sl):
        continue

    risk = abs(entry - sl)
    if risk <= 0:
        continue

    outcome = "TIMEOUT"
    exit_price = None
    exit_time = None
    previous_time = None

    for _, bar in future.head(MAX_HOLD_BARS).iterrows():
        current_time = bar["time"]

        if previous_time is not None:
            gap = (current_time - previous_time).total_seconds()

            if gap > MAX_GAP_SECONDS:
                outcome = "DATA_GAP"
                break

        previous_time = current_time

        high = float(bar["high"])
        low = float(bar["low"])

        if direction == -1:
            hit_sl = high >= sl
            hit_tp = low <= tp
        else:
            hit_sl = low <= sl
            hit_tp = high >= tp

        # Conservative assumption: SL first.
        if hit_sl:
            outcome = "LOSS"
            exit_price = sl
            exit_time = current_time
            break

        if hit_tp:
            outcome = "WIN"
            exit_price = tp
            exit_time = current_time
            break

        exit_price = float(bar["close"])
        exit_time = current_time

    if exit_time is None:
        continue

    pnl_r = (
        direction * (exit_price - entry) / risk
    )

    if outcome == "TIMEOUT":
        pnl_r = float(pnl_r)

    results.append({
        "entry_time": entry_time,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "outcome": outcome,
        "pnl_r": pnl_r,
    })

    busy_until = exit_time

result = pd.DataFrame(results)

if result.empty:
    raise SystemExit("No valid trades")

result.to_csv("backtests/xauusdc_trade_results.csv", index=False)

print("\n===== BACKTEST RESULTS =====")
print(result.to_string(index=False))

print("\n===== SUMMARY =====")
print("Trades:", len(result))
print("Wins:", (result["outcome"] == "WIN").sum())
print("Losses:", (result["outcome"] == "LOSS").sum())
print("Other:", (~result["outcome"].isin(["WIN", "LOSS"])).sum())
print("Total R:", round(result["pnl_r"].sum(), 2))
print("Average R:", round(result["pnl_r"].mean(), 3))

completed = result[result["outcome"].isin(["WIN", "LOSS"])]

if len(completed):
    print(
        "Win rate:",
        round((completed["outcome"] == "WIN").mean() * 100, 2),
        "%"
    )
