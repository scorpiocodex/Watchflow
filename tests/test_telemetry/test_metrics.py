import sqlite3
from pathlib import Path

from watchflow.telemetry.metrics import TelemetryStore


def test_telemetry_store_initializes_db(tmp_path: Path):
    db_path = tmp_path / "metrics.db"
    store = TelemetryStore(db_path=db_path)
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "pipeline_metrics" in tables
    assert "resource_metrics" in tables
    store.close()


def test_telemetry_store_records_pipeline_event(tmp_path: Path):
    db_path = tmp_path / "metrics.db"
    store = TelemetryStore(db_path=db_path)

    store.record_pipeline("build_app", True, 450.5)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT pipeline_name, success, duration_ms FROM pipeline_metrics")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "build_app"
    assert rows[0][1] == 1  # success
    assert rows[0][2] == 450.5

    conn.close()
    store.close()


def test_telemetry_store_memory_metrics(tmp_path: Path):
    db_path = tmp_path / "metrics.db"
    store = TelemetryStore(db_path=db_path)

    store.record_pipeline("fail_app", False, 100.0)
    assert store.pipeline_count == 1
    assert store.failure_count == 1

    store.record_event()
    assert store.event_count == 1

    store.close()
