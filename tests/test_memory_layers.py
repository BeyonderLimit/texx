from datetime import datetime, timedelta

from services.memory import MemoryService
from storage.database import Database


def _iso(dt):
    return dt.replace(microsecond=0).isoformat(sep=" ")


def test_add_defaults_to_persistent(tmp_path):
    ms = MemoryService(Database(tmp_path / "m.db"))
    mid = ms.add("I prefer dark mode", category="PREFERENCE")
    row = ms.get(mid)
    assert row["layer"] == "persistent"


def test_add_discussion_sets_layer_and_expiry(tmp_path):
    ms = MemoryService(Database(tmp_path / "m.db"))
    now = datetime(2026, 1, 1, 12, 0, 0)
    mid = ms.add_discussion("working on the report", now=now)
    row = ms.get(mid)
    assert row["layer"] == "discussion"
    # expires ~7 days out
    exp = datetime.fromisoformat(row["expires_at"])
    assert 6 <= (exp - now).days <= 7


def test_search_filters_by_layer(tmp_path):
    ms = MemoryService(Database(tmp_path / "m.db"))
    ms.add("alpha is a persistent fact", category="FACT")
    ms.add_discussion("alpha mentioned in discussion")
    persistent = ms.search("alpha", layers=["persistent"])
    discussion = ms.search("alpha", layers=["discussion"])
    assert len(persistent) == 1 and persistent[0]["layer"] == "persistent"
    assert len(discussion) == 1 and discussion[0]["layer"] == "discussion"


def test_compact_discussion_removes_old(tmp_path):
    ms = MemoryService(Database(tmp_path / "m.db"))
    ms.add_discussion("old discussion", now=datetime(2026, 1, 1))
    # now set far in the future so cutoff passes the 2026-01-01 row
    future = datetime(2026, 1, 20)
    removed = ms.compact_discussion(older_than_days=7, now=future)
    assert removed == 1
    assert ms.search("old discussion", layers=["discussion"]) == []


def test_prune_daily(tmp_path):
    ms = MemoryService(Database(tmp_path / "m.db"))
    ms.add_daily("a daily note from long ago", expires_at=datetime(2020, 1, 1), now=datetime(2020, 1, 1))
    removed = ms.prune_daily(older_than_days=90, now=datetime(2026, 1, 1))
    assert removed == 1
    assert ms.db.query("SELECT COUNT(*) AS c FROM memories WHERE layer='daily'")[0]["c"] == 0


def test_summarize_yesterday_discussion_folds_and_deletes(tmp_path):
    ms = MemoryService(Database(tmp_path / "m.db"))
    # 'now' is 2026-03-01, so yesterday is 2026-02-28
    now = datetime(2026, 3, 1, 9, 0, 0)
    yest = datetime(2026, 2, 28, 10, 0, 0)
    ms.add_discussion("user said alpha", role="user", now=yest)
    ms.add_discussion("assistant replied beta", role="assistant", now=yest)

    n = ms.summarize_yesterday_discussion(llm=None, now=now)
    assert n == 2
    daily = ms.db.query("SELECT * FROM memories WHERE layer='daily'")
    assert len(daily) == 1
    assert "alpha" in daily[0]["content"] and "beta" in daily[0]["content"]
    # source discussion compacted away
    assert ms.db.query("SELECT COUNT(*) AS c FROM memories WHERE layer='discussion'")[0]["c"] == 0


def test_summarize_yesterday_uses_llm_when_provided(tmp_path):
    ms = MemoryService(Database(tmp_path / "m.db"))
    yest = datetime(2026, 2, 28, 10, 0, 0)
    now = datetime(2026, 3, 1, 9, 0, 0)
    ms.add_discussion("user said alpha", role="user", now=yest)

    class FakeLLM:
        def condense(self, text):
            return "SUMMARY(" + text[:5] + ")"

    n = ms.summarize_yesterday_discussion(llm=FakeLLM(), now=now)
    assert n == 1
    daily = ms.db.query("SELECT * FROM memories WHERE layer='daily'")
    assert daily[0]["content"].startswith("SUMMARY(")
