"""Bounded local analysis logs; never records credentials or account identifiers."""

import json
import logging
from collections import Counter, deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


def record_analysis(path, plan, elapsed_ms, error_type=None, *, max_bytes=2_000_000):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": 1,
        "event": "analysis",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": round(elapsed_ms, 2),
        "error_type": error_type,
        "plan": plan,
    }
    payload = json.dumps(event, ensure_ascii=True, allow_nan=False)
    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=3, encoding="utf-8")
    try:
        # Write directly so filesystem failures propagate to the terminal's error handler.
        record = logging.LogRecord("assistant", logging.INFO, "", 0, payload, (), None)
        if handler.shouldRollover(record):
            handler.doRollover()
        handler.stream.write(payload + "\n")
        handler.flush()
    finally:
        handler.close()


def summarize_log(path, limit=200):
    path = Path(path)
    if not path.exists():
        return "Chua co log phan tich moi. Nhan Enter de tao ban ghi."
    statuses, reasons = Counter(), Counter()
    issues = Counter()
    errors = 0
    latest = None
    with path.open(encoding="utf-8") as handle:
        lines = deque(handle, maxlen=limit)
    for line in lines:
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or event.get("event") != "analysis":
                raise ValueError("Not an analysis event")
            plan = event["plan"]
            if not isinstance(plan, dict) or not isinstance(plan.get("status"), str):
                raise ValueError("Invalid plan")
            references = plan.get("reference_scenarios", [])
            if not isinstance(references, list):
                raise ValueError("Invalid reference scenarios")
            statuses[plan["status"]] += 1
            reason = plan.get("reason")
            if isinstance(reason, str):
                reasons[reason] += 1
            current_issues = set()
            if event.get("error_type"):
                current_issues.add("Loi xu ly: " + str(event["error_type"]))
            kelly = plan.get("kelly")
            if isinstance(kelly, dict) and kelly.get("status") != "READY":
                current_issues.add("Kelly: " + str(kelly.get("status")))
            risk = plan.get("account_risk")
            if isinstance(risk, dict) and risk.get("status") != "READY":
                current_issues.add("Rui ro tai khoan: " + str(risk.get("status")))
            for candidate in [plan, *references]:
                if isinstance(candidate, dict) and isinstance(candidate.get("sizing_note"), str):
                    current_issues.add("Lot: " + candidate["sizing_note"])
            issues.update(sorted(current_issues))
            latest = event.get("recorded_at_utc")
        except (ValueError, KeyError, TypeError):
            errors += 1
    result = [
        f"LOG: {sum(statuses.values())} lan phan tich gan nhat (toi da {limit} dong)",
        " | ".join(f"{status}: {count}" for status, count in statuses.items())
        or "Chua co ban ghi hop le",
    ]
    if latest:
        result.append(f"Ban ghi cuoi (UTC): {latest}")
    result.extend(f"{count} lan: {reason}" for reason, count in reasons.most_common(3))
    result.extend(f"{count} lan: {issue}" for issue, count in issues.most_common(5))
    if errors:
        result.append(f"Bo qua {errors} dong log hong/khong dung dinh dang")
    return "\n".join(result)
