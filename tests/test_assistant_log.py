import json

from src.strategies.assistant_log import record_analysis, summarize_log


def test_event_records_analysis_and_summary(tmp_path):
    path = tmp_path / "events.jsonl"
    record_analysis(path, {"status": "WAIT", "reason": "No valid setup"}, 12.345)
    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["elapsed_ms"] == 12.35
    assert event["schema_version"] == 1
    assert event["error_type"] is None
    assert "WAIT: 1" in summarize_log(path)


def test_bad_log_lines_are_reported_without_losing_valid_records(tmp_path):
    path = tmp_path / "events.jsonl"
    record_analysis(path, {"status": "BLOCKED", "reason": "Disconnected"}, 100, "ValueError")
    with path.open("a", encoding="utf-8") as handle:
        handle.write('broken\n[]\n{"event":"analysis","plan":null}\n')
    text = summarize_log(path)
    assert "BLOCKED: 1" in text
    assert "3 dong log hong" in text


def test_rotation_keeps_bounded_backups(tmp_path):
    path = tmp_path / "events.jsonl"
    for _ in range(10):
        record_analysis(path, {"status": "WAIT", "reason": "No setup"}, 1, max_bytes=300)
    assert path.exists() and path.with_name("events.jsonl.3").exists()
    assert not path.with_name("events.jsonl.4").exists()
    assert "WAIT:" in summarize_log(path)


def test_missing_log_is_explained(tmp_path):
    assert "Chua co log" in summarize_log(tmp_path / "missing.jsonl")
