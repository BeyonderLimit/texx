import logging
import os
from pathlib import Path


def log_path() -> Path:
    base = Path(os.environ.get("HOME", os.path.expanduser("~"))) / ".local" / "share" / "texx"
    base.mkdir(parents=True, exist_ok=True)
    return base / "texx.log"


_logger = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger("texx")
        if not _logger.handlers:
            handler = logging.FileHandler(log_path())
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            )
            _logger.addHandler(handler)
            _logger.setLevel(logging.INFO)
    return _logger


def log_info(msg: str, **extra) -> None:
    get_logger().info(_fmt(msg, extra))


def log_error(msg: str, **extra) -> None:
    get_logger().error(_fmt(msg, extra))


def log_fault(msg: str, **extra) -> None:
    get_logger().warning("FAULT " + _fmt(msg, extra))


def _fmt(msg: str, extra: dict) -> str:
    if extra:
        return f"{msg} :: {extra}"
    return msg


def recent(lines: int = 40) -> list:
    """Return the last `lines` log entries (oldest first) for display."""
    path = log_path()
    if not path.exists():
        return []
    with open(path) as f:
        return f.read().splitlines()[-lines:]
