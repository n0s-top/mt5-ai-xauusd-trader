"""Historical signal test for XAUUSDc. No order execution."""

from pathlib import Path
import pandas as pd

from src.strategies.scalping_data import prepare_scalping_data
from src.strategies.xauusd_m1_scalper import XAUUSDM1Scalper


CSV_PATH = (
    Path.home()
    / ".var/app/com.usebottles.bottles/data/bottles/bottles/"
      "MetaTrader5/drive_c/users/han/AppData/Roaming/"
      "MetaQuotes/Terminal/Common/Files/"
      "MT5_XAUUSDc_M1.csv"
)

OUTPUT = Path("backtests/xauusdc_signals.csv")


def main():
    df = pd.read_csv(CSV_PATH, encoding="utf-16")

    df["time"] = pd.to_datetime(
        df["time"], unit="s", utc=True
    )

    df = df.sort_values("time").reset_index(drop=True)

    if df["time"].duplicated().any():
        raise ValueError("Duplicate timestamps")

    scalper = XAUUSDM1Scalper()

    signals = []

    # M15 EMA200 requires approximately 3,000 M1 candles.
    # Extra history allows indicator warm-up.
    start = 3300

    print(f"Total M1 candles: {len(df)}")
    print(f"Testing from index: {start}")

    if len(df) <= start:
        raise SystemExit("Insufficient historical data")

    for i in range(start, len(df)):
        # Evaluate after candle i-1 has closed.
        # Candle i is never included in signal generation.
        history = df.iloc[:i].copy()

        last_open_time = history["time"].iloc[-1]
        asof = last_open_time + pd.Timedelta(minutes=1)

        data = prepare_scalping_data(
            history,
            asof=asof,
        )

        if min(
            len(data["M1"]),
            len(data["M5"]),
            len(data["M15"]),
        ) < 220:
            continue

        signal = scalper.predict(
            data["M1"],
            data["M5"],
            data["M15"],
        )

        signals.append({
            "time": asof.isoformat(),
            "direction": signal.direction,
            "confidence": signal.confidence,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "reason": signal.reason,
        })

        if (i - start) % 200 == 0:
            print(f"Processed {i}/{len(df)} candles")

    result = pd.DataFrame(signals)

    if result.empty:
        print("No evaluable signals")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False)

    print("\n===== BACKTEST SIGNAL SUMMARY =====")
    print("Evaluated:", len(result))
    print("BUY:", int((result["direction"] == 1).sum()))
    print("SELL:", int((result["direction"] == -1).sum()))
    print("HOLD:", int((result["direction"] == 0).sum()))

    trades = result[result["direction"] != 0]

    print("\n===== BUY/SELL SIGNALS =====")

    if trades.empty:
        print("No BUY/SELL signals found")
    else:
        print(trades.to_string(index=False))

    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
