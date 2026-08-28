from datetime import datetime, timedelta

from services.owner import OwnerProfile


def _memories():
    return [
        {"content": "name is Sam", "category": "PROFILE"},
        {"content": "prefers terse replies", "category": "PREFERENCE"},
        {"content": "works with Alice on texx", "category": "PEOPLE"},
        {"content": "building texx assistant", "category": "PROJECT"},
        {"content": "born in spring", "category": "FACT"},
    ]


def test_owner_build_orders_categories(tmp_path):
    owner = OwnerProfile(path=tmp_path / "OWNER.md")
    text = owner.build(_memories(), llm=None)
    assert text.startswith("# OWNER.md")
    # categories appear in the curated display order
    pos = {c: text.find(f"## {c}") for c in ["PROFILE", "PREFERENCE", "PEOPLE", "PROJECT", "FACT"]}
    assert pos["PROFILE"] < pos["PREFERENCE"] < pos["PEOPLE"] < pos["PROJECT"] < pos["FACT"]


def test_owner_regen_force_writes_file(tmp_path):
    owner = OwnerProfile(path=tmp_path / "OWNER.md")
    ok = owner.regen(_memories(), llm=None, force=True)
    assert ok is True
    assert owner.exists()
    assert "Sam" in owner.read()


def test_owner_maybe_regen_debounced(tmp_path):
    owner = OwnerProfile(path=tmp_path / "OWNER.md")
    # not enough dirty writes and within cooldown -> no write
    now = datetime(2026, 1, 1, 12, 0, 0)
    assert owner.maybe_regen(_memories(), llm=None, now=now) is False
    assert not owner.exists()
    # mark dirty enough to cross threshold -> regen happens
    for _ in range(25):
        owner.mark_dirty()
    assert owner.maybe_regen(_memories(), llm=None, now=now) is True
    assert owner.exists()


def test_owner_cooldown_blocks_rapid_regen(tmp_path):
    owner = OwnerProfile(path=tmp_path / "OWNER.md")
    for _ in range(25):
        owner.mark_dirty()
    now = datetime(2026, 1, 1, 12, 0, 0)
    assert owner.regen(_memories(), llm=None, now=now, force=False) is True
    # immediately again: dirty reset + within cooldown -> blocked
    for _ in range(25):
        owner.mark_dirty()
    assert owner.regen(_memories(), llm=None, now=now + timedelta(minutes=1), force=False) is False


def test_owner_llm_condenses(tmp_path):
    class FakeLLM:
        def condense(self, text):
            return "OWNER:" + text.splitlines()[0]

    owner = OwnerProfile(path=tmp_path / "OWNER.md")
    owner.regen(_memories(), llm=FakeLLM(), force=True)
    assert owner.read().startswith("OWNER:# OWNER.md")
