import sqlite3
from pathlib import Path

from watchflow.core.events import FileSystemEvent, FSEventType, IntentEvent
from watchflow.core.wal import WriteAheadLog


def test_wal_initializes_db(tmp_path: Path):
    db_path = tmp_path / "wal.db"
    wal = WriteAheadLog(db_path=db_path)
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "events" in tables
    wal.close()


def test_wal_record_and_replay_fs_event(tmp_path: Path):
    db_path = tmp_path / "wal.db"
    wal = WriteAheadLog(db_path=db_path)

    event = FileSystemEvent(
        path="/some/file.txt",
        event_type=FSEventType.MODIFIED,
        watcher_name="src",
    )

    wal.record(event)

    events = wal.read_all()
    assert len(events) == 1

    wal_evt = events[0]
    assert wal_evt["event_type"] == "fs"
    assert wal_evt["payload"]["path"] == "/some/file.txt"
    assert wal_evt["payload"]["event_type"] == "MODIFIED"

    wal.close()


def test_wal_record_intent_event(tmp_path: Path):
    db_path = tmp_path / "wal.db"
    wal = WriteAheadLog(db_path=db_path)

    event = IntentEvent(
        intent_name="run_tests",
        pipeline_name="test_pipeline",
        confidence=0.99,
    )

    wal.record(event)

    events = wal.read_all()
    assert len(events) == 1
    assert events[0]["event_type"] == "intent"
    assert events[0]["payload"]["intent_name"] == "run_tests"
    assert events[0]["payload"]["pipeline_name"] == "test_pipeline"

    wal.close()


def test_wal_clear(tmp_path: Path):
    db_path = tmp_path / "wal.db"
    wal = WriteAheadLog(db_path=db_path)

    event = FileSystemEvent(
        path="/some/file.txt",
        event_type=FSEventType.MODIFIED,
        watcher_name="src",
    )
    wal.record(event)
    assert len(wal.read_all()) == 1

    wal.clear()
    assert len(wal.read_all()) == 0

    wal.close()
