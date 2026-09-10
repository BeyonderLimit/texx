import sqlite3 as _sq

import pytest

import storage.database as sdb
from services.memory import MemoryService
from services.sessionlog import SessionLogService
from storage.database import Database


class CountingConn(_sq.Connection):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.committed = 0

    def commit(self):
        self.committed += 1
        super().commit()


def _counting_db(tmp_path, name):
    orig = sdb.sqlite3.Connection
    sdb.sqlite3.Connection = CountingConn
    try:
        db = Database(tmp_path / name)
    finally:
        sdb.sqlite3.Connection = orig
    db.conn.committed = 0
    return db


def test_transaction_batches_writes_into_one_commit(tmp_path):
    db = _counting_db(tmp_path, "t.db")
    with db.transaction():
        db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("a", "1", "x"))
        db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("b", "2", "x"))
        db.execute("UPDATE settings SET value = 'z' WHERE key = 'a'")
    assert db.conn.committed == 1
    row = db.conn.execute("SELECT count(*) FROM settings").fetchone()[0]
    assert row == 2
    assert db.conn.execute("SELECT value FROM settings WHERE key = 'a'").fetchone()[0] == "z"


def test_transaction_nested_flattens(tmp_path):
    db = _counting_db(tmp_path, "n.db")
    with db.transaction():
        db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("a", "1", "x"))
        with db.transaction():
            db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("b", "2", "x"))
        db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("c", "3", "x"))
    assert db.conn.committed == 1
    n = db.conn.execute("SELECT count(*) FROM settings").fetchone()[0]
    assert n == 3


def test_transaction_rolls_back_whole_group_on_error(tmp_path):
    db = _counting_db(tmp_path, "r.db")


    class Boom(Exception):
        pass


    with pytest.raises(Boom):
        with db.transaction():
            db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("a", "1", "x"))
            db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("b", "2", "x"))
            raise Boom()
    assert db.conn.execute("SELECT count(*) FROM settings").fetchone()[0] == 0
    assert db.conn.committed == 0
    with db.transaction():
        db.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("c", "3", "x"))
    assert db.conn.execute("SELECT count(*) FROM settings").fetchone()[0] == 1


def test_log_turn_plus_discussion_single_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(sdb.sqlite3, "Connection", CountingConn)
    db = Database(tmp_path / "s.db")
    db.conn.committed = 0
    sl = SessionLogService(db)
    mem = MemoryService(db)
    with db.transaction():
        sl.log_turn("user", "folded")
        mem.add_discussion("folded", source="session", role="user")
    assert db.conn.committed == 1
    assert db.conn.execute("SELECT count(*) FROM session_turns").fetchone()[0] == 1
    assert db.conn.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
    assert db.conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


def test_wal_pragma_applied(tmp_path):
    db = Database(tmp_path / "wal.db")
    mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
    sync = db.conn.execute("PRAGMA synchronous").fetchone()[0]
    assert mode == "wal"
    assert sync == 1