import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

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
    last_processed = None

    logging.info("XAUUSDc M1 Scalper started (SIGNAL ONLY)")
    logging.info("Source: %s", CSV_PATH)

    while True:
        try:
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

            if last_processed == latest:
                time.sleep(POLL_SECONDS)
                continue

            if min(len(data["M1"]), len(data["M5"]), len(data["M15"])) < 220:
                logging.warning("Chưa đủ dữ liệu EMA200")
                time.sleep(POLL_SECONDS)
                continue

            signal = scalper.predict(data["M1"], data["M5"], data["M15"])

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
