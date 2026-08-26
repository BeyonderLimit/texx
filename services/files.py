from pathlib import Path

from rapidfuzz import fuzz

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".cache",
    ".mozilla", ".config", "site-packages", ".local", "snap", ".npm",
}

DEFAULT_ROOTS = ("Documents", "Downloads", "Desktop", "")


class FileSearchService:
    def __init__(self, home: Path | None = None, roots: tuple[str, ...] | None = None,
                 max_depth: int = 6):
        self.home = Path(home or Path.home())
        self.roots = roots or DEFAULT_ROOTS
        self.max_depth = max_depth

    def find(self, query: str, limit: int = 10) -> list[Path]:
        q = query.strip().lower().replace(" ", "")
        if not q:
            return []
        scored: list[tuple[float, Path]] = []
        for root in self.roots:
            base = self.home / root if root else self.home
            if not base.is_dir():
                continue
            for path in self._walk(base):
                name = path.name.lower()
                compact = name.replace(" ", "").replace("_", "").replace("-", "")
                score = max(
                    fuzz.partial_ratio(q, compact),
                    fuzz.partial_ratio(q, name),
                )
                if q in compact:
                    score = max(score, 95.0)
                if score >= 60:
                    scored.append((score, path))
        scored.sort(key=lambda pair: (-pair[0], str(pair[1]).lower()))
        return [path for _, path in scored[:limit]]

    def _walk(self, base: Path):
        stack = [(base, 0)]
        while stack:
            current, depth = stack.pop()
            try:
                entries = sorted(current.iterdir(), reverse=True)
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                    continue
                yield entry
                if entry.is_dir() and depth < self.max_depth:
                    stack.append((entry, depth + 1))
