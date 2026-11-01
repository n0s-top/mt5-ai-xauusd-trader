import argparse
import csv
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.strategies.entry_support import build_entry_plan
from src.strategies.scalping_data import prepare_scalping_data
from src.strategies.xauusd_m1_scalper import XAUUSDM1Scalper

SYMBOL = "XAUUSDc"
POLL_SECONDS = 5
MAX_FILE_AGE = 30
MAX_CANDLE_AGE = 180

COMMON = (
    Path.home() / ".var/app/com.usebottles.bottles/data/bottles/bottles/"
    "MetaTrader5/drive_c/users/han/AppData/Roaming/"
    "MetaQuotes/Terminal/Common/Files"
)
if os.name == "nt":
    COMMON = Path(os.environ.get("APPDATA", Path.home())) / "MetaQuotes/Terminal/Common/Files"

CSV_PATH = COMMON / f"MT5_{SYMBOL}_M1.csv"
LOG_PATH = Path("logs/scalper_signals.csv")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

scalper = XAUUSDM1Scalper()


def load_data():
    # EA ghi đè CSV định kỳ; thử lại nếu đọc đúng lúc đang ghi.
    for attempt in range(3):
        try:
            df = pd.read_csv(CSV_PATH, encoding="utf-16")

            required = {"time", "open", "high", "low", "close", "tick_volume"}

            if not required.issubset(df.columns):
                raise ValueError("CSV thiếu cột dữ liệu")

            if df.empty:
                raise ValueError("CSV rỗng")

            for column in ("time", "open", "high", "low", "close", "tick_volume"):
                df[column] = pd.to_numeric(df[column], errors="raise")

            if df.isna().any().any():
                raise ValueError("CSV chứa dữ liệu thiếu")

            if df["time"].duplicated().any():
                raise ValueError("Timestamp bị trùng")

            if not df["time"].is_monotonic_increasing:
                raise ValueError("Timestamp không tăng dần")

            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

            return df

        except (
            OSError,
            UnicodeError,
            pd.errors.ParserError,
            ValueError,
        ):
            if attempt == 2:
                raise
            time.sleep(0.5)


def save_signal(candle_time, signal):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    exists = LOG_PATH.exists()

    with LOG_PATH.open("a", newline="") as file:
        writer = csv.writer(file)

        if not exists:
            writer.writerow(
                [
                    "processed_at_utc",
                    "symbol",
                    "candle_time_utc",
                    "direction",
                    "confidence",
                    "stop_loss",
                    "take_profit",
                    "reason",
                ]
            )

        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                SYMBOL,
                candle_time.isoformat(),
                signal.direction,
                signal.confidence,
                signal.stop_loss,
                signal.take_profit,
                signal.reason,
            ]
        )


def main():
    global CSV_PATH, SYMBOL
    parser = argparse.ArgumentParser(description="Manual entry assistant (no order submission)")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--quote", type=Path, help="Live broker quote CSV exported by MT5 bridge")
    parser.add_argument("--equity", type=float, help="Account equity in account currency")
    parser.add_argument("--risk-percent", type=float, default=0.5)
    parser.add_argument("--plan", type=Path, default=Path("logs/entry_plan.json"))
    args = parser.parse_args()
    if args.equity is not None and (not 0 < args.equity < float("inf")):
        parser.error("--equity must be finite and positive")
    if not 0 < args.risk_percent <= 100:
        parser.error("--risk-percent must be in (0, 100]")
    SYMBOL = args.symbol
    CSV_PATH = args.csv or COMMON / f"MT5_{SYMBOL}_M1.csv"
    quote_path = args.quote or CSV_PATH.with_name(f"MT5_{SYMBOL}_quote.csv")
    last_processed = None

    logging.info("XAUUSDc M1 Scalper started (SIGNAL ONLY)")
    logging.info("Source: %s", CSV_PATH)

    while True:
        try:
            # Remove the previous actionable plan before validating a fresh snapshot.
            args.plan.parent.mkdir(parents=True, exist_ok=True)
            args.plan.write_text(json.dumps({"status": "WAIT", "reason": "Awaiting fresh validation"}), encoding="utf-8")
            if not CSV_PATH.exists():
                logging.warning("Chưa tìm thấy CSV")
                time.sleep(POLL_SECONDS)
                continue

            now = datetime.now(timezone.utc)

            file_age = now.timestamp() - CSV_PATH.stat().st_mtime

            if file_age < -5 or file_age > MAX_FILE_AGE:
                logging.warning("CSV không cập nhật: file_age=%.1fs", file_age)
                time.sleep(POLL_SECONDS)
                continue

            df = load_data()

            data = prepare_scalping_data(df, asof=pd.Timestamp(now))
            if data["M1"].empty:
                logging.warning("Chưa có nến đóng")
                time.sleep(POLL_SECONDS)
                continue
            latest = data["M1"].index[-1]
            candle_age = (now - latest.to_pydatetime()).total_seconds()

            if candle_age < 60 or candle_age > MAX_CANDLE_AGE:
                logging.warning("Dữ liệu nến không hợp lệ hoặc quá cũ: %.1fs", candle_age)
                time.sleep(POLL_SECONDS)
                continue

            if last_processed == latest and args.equity is None:
                time.sleep(POLL_SECONDS)
                continue

            if min(len(data["M1"]), len(data["M5"]), len(data["M15"])) < 220:
                logging.warning("Chưa đủ dữ liệu EMA200")
                time.sleep(POLL_SECONDS)
                continue

            quote = None
            if args.equity is not None:
                quote = pd.read_csv(quote_path, encoding="utf-16").iloc[-1].to_dict()
                quote_age = now.timestamp() - float(quote["time"])
                if quote.get("symbol") != SYMBOL or not 0 <= quote_age <= 15:
                    raise ValueError("Quote symbol mismatch or stale quote")
            spread = float(quote["ask"]) - float(quote["bid"]) if quote else None
            signal = scalper.predict(data["M1"], data["M5"], data["M15"], spread=spread)
            if quote is not None:
                plan = build_entry_plan(signal, quote, equity=args.equity,
                                        risk_percent=args.risk_percent).to_dict()
                plan.update(symbol=SYMBOL, candle_time=latest.isoformat(),
                            generated_at_utc=now.isoformat(),
                            expires_at_utc=datetime.fromtimestamp(
                                min(float(quote["time"]) + 15,
                                    latest.timestamp() + MAX_CANDLE_AGE), timezone.utc
                            ).isoformat())
                args.plan.write_text(json.dumps(plan, indent=2), encoding="utf-8")
                logging.info("Entry plan: %s", plan)

            logging.info(
                "%s | %s | Direction=%s | Confidence=%s | SL=%s | TP=%s | Reason=%s",
                SYMBOL,
                latest.isoformat(),
                signal.direction,
                signal.confidence,
                signal.stop_loss,
                signal.take_profit,
                signal.reason,
            )

            if last_processed != latest:
                save_signal(latest, signal)
            last_processed = latest

        except KeyboardInterrupt:
            logging.info("Scalper stopped")
            break

        except Exception:
            logging.exception("Lỗi xử lý dữ liệu")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
