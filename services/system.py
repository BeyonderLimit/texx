import json
import subprocess


def launch_detached(argv: list[str]) -> None:
    """Launch a GUI/external app so it never shares the TUI's terminal or
    process group — output is discarded, and it survives Ctrl-C / terminal close."""
    subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


APP_ALIASES = {
    "firefox": ["fire fox", "mozilla", "firefox browser"],
    "files": ["file manager", "my files"],
}

DEFAULT_OPEN_MAP = {
    "firefox": ["firefox"],
    "chrome": ["google-chrome"],
    "chromium": ["chromium"],
    "files": ["xdg-open", "."],
    "terminal": ["xdg-open", "."],
    "calculator": ["gnome-calculator"],
    "text editor": ["gedit"],
}

DEFAULT_CLOSE_MAP = {
    "firefox": "firefox",
    "chrome": "chrome",
    "chromium": "chromium",
    "spotify": "spotify",
    "calculator": "gnome-calculator",
}

OPEN_KEY = "app_open_map"
CLOSE_KEY = "app_close_map"
DISABLED_OPEN_KEY = "app_disabled_open"
DISABLED_CLOSE_KEY = "app_disabled_close"


class UnknownApplication(Exception):
    pass


def normalize(name: str) -> str:
    name = name.strip().lower()
    for canonical, aliases in APP_ALIASES.items():
        if name in aliases:
            return canonical
    return name


def _load_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _load_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class SystemService:
    def __init__(self, settings=None):
        self.settings = settings

    def _disabled(self, key: str) -> set[str]:
        return set(_load_list(self.settings.get(key)) if self.settings else [])

    def open_map(self) -> dict[str, list[str]]:
        custom = _load_json(self.settings.get(OPEN_KEY)) if self.settings else {}
        disabled = self._disabled(DISABLED_OPEN_KEY)
        merged = {**DEFAULT_OPEN_MAP, **custom}
        return {k: v for k, v in merged.items() if k not in disabled}

    def close_map(self) -> dict[str, str]:
        custom = _load_json(self.settings.get(CLOSE_KEY)) if self.settings else {}
        disabled = self._disabled(DISABLED_CLOSE_KEY)
        merged = {**DEFAULT_CLOSE_MAP, **custom}
        return {k: v for k, v in merged.items() if k not in disabled}

    def add_open(self, name: str, argv: list[str]) -> None:
        custom = _load_json(self.settings.get(OPEN_KEY)) if self.settings else {}
        norm = normalize(name)
        custom[norm] = argv
        self._save(OPEN_KEY, custom)
        self._clear_disabled(DISABLED_OPEN_KEY, norm)

    def remove_open(self, name: str) -> bool:
        return self._disable(OPEN_KEY, DISABLED_OPEN_KEY, name, DEFAULT_OPEN_MAP)

    def add_close(self, name: str, process: str) -> None:
        custom = _load_json(self.settings.get(CLOSE_KEY)) if self.settings else {}
        norm = normalize(name)
        custom[norm] = process
        self._save(CLOSE_KEY, custom)
        self._clear_disabled(DISABLED_CLOSE_KEY, norm)

    def remove_close(self, name: str) -> bool:
        return self._disable(CLOSE_KEY, DISABLED_CLOSE_KEY, name, DEFAULT_CLOSE_MAP)

    def _save(self, key: str, data: dict):
        if self.settings:
            self.settings.set(key, json.dumps(data))

    def _save_list(self, key: str, data: list):
        if self.settings:
            self.settings.set(key, json.dumps(data))

    def _clear_disabled(self, disabled_key: str, norm: str) -> None:
        if not self.settings:
            return
        disabled = self._disabled(disabled_key)
        if norm in disabled:
            disabled.discard(norm)
            self._save_list(disabled_key, sorted(disabled))

    def _disable(self, open_key: str, disabled_key: str, name: str, default_map: dict) -> bool:
        if not self.settings:
            return False
        norm = normalize(name)
        custom = _load_json(self.settings.get(open_key))
        was_custom = custom.pop(norm, None) is not None
        self._save(open_key, custom)
        was_effective = was_custom or norm in default_map
        if was_effective:
            disabled = self._disabled(disabled_key)
            disabled.add(norm)
            self._save_list(disabled_key, sorted(disabled))
        return was_effective

    def open_app(self, name: str):
        command = self.open_map().get(normalize(name))
        if not command:
            raise UnknownApplication(name)
        launch_detached(command)

    def close_app(self, name: str):
        process = self.close_map().get(normalize(name))
        if not process:
            raise UnknownApplication(name)
        subprocess.run(["pkill", "-f", process], check=False)
