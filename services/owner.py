from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR

OWNER_PATH = Path(DATA_DIR) / "OWNER.md"
REGEN_COOLDOWN = timedelta(minutes=10)
REGEN_DIRTY_THRESHOLD = 20

# Curated categories shown in OWNER.md, in display order.
OWNER_CATEGORIES = ["PROFILE", "PREFERENCE", "PEOPLE", "PROJECT", "FACT"]


class OwnerProfile:
    """A compact, curated owner profile (OWNER.md). Unlike memory, it is a
    hand-shaped summary, not a raw history store. Regeneration is debounced so
    it never runs per turn."""

    def __init__(self, path=OWNER_PATH):
        self.path = Path(path)
        self._last_regen = None
        self._dirty = 0

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> str:
        if self.path.exists():
            return self.path.read_text()
        return ""

    def mark_dirty(self):
        self._dirty += 1

    def build(self, memories: list, llm=None) -> str:
        by_cat: dict[str, list] = {}
        for m in memories:
            by_cat.setdefault(m["category"], []).append(m["content"])
        lines = ["# OWNER.md", "",
                 "Curated owner profile — a summary, not a raw history store.", ""]
        for cat in OWNER_CATEGORIES:
            items = by_cat.get(cat)
            if items:
                lines.append(f"## {cat}")
                for c in items[:25]:
                    lines.append(f"- {c}")
                lines.append("")
        text = "\n".join(lines).rstrip() + "\n"
        if llm is not None:
            try:
                condensed = llm.condense(text)
                if condensed:
                    text = condensed
            except Exception:
                pass
        return text

    def regen(self, memories: list, llm=None, now: datetime | None = None,
              force: bool = False) -> bool:
        now = now or datetime.now()
        if not force:
            if self._last_regen is not None and (now - self._last_regen) < REGEN_COOLDOWN:
                return False
            if self._dirty < REGEN_DIRTY_THRESHOLD:
                return False
        text = self.build(memories, llm=llm)
        self.path.write_text(text)
        self._last_regen = now
        self._dirty = 0
        return True

    def maybe_regen(self, memories: list, llm=None, now: datetime | None = None) -> bool:
        return self.regen(memories, llm=llm, now=now, force=False)
