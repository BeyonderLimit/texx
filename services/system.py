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


class SystemService:
    def __init__(self, settings=None):
        self.settings = settings

    def open_map(self) -> dict[str, list[str]]:
        custom = _load_json(self.settings.get(OPEN_KEY)) if self.settings else {}
        return {**DEFAULT_OPEN_MAP, **custom}

    def close_map(self) -> dict[str, str]:
        custom = _load_json(self.settings.get(CLOSE_KEY)) if self.settings else {}
        return {**DEFAULT_CLOSE_MAP, **custom}

    def add_open(self, name: str, argv: list[str]) -> None:
        custom = _load_json(self.settings.get(OPEN_KEY)) if self.settings else {}
        custom[normalize(name)] = argv
        self._save(OPEN_KEY, custom)

    def remove_open(self, name: str) -> bool:
        return self._remove(OPEN_KEY, name)

    def add_close(self, name: str, process: str) -> None:
        custom = _load_json(self.settings.get(CLOSE_KEY)) if self.settings else {}
        custom[normalize(name)] = process
        self._save(CLOSE_KEY, custom)

    def remove_close(self, name: str) -> bool:
        return self._remove(CLOSE_KEY, name)

    def _save(self, key: str, data: dict):
        if self.settings:
            self.settings.set(key, json.dumps(data))

    def _remove(self, key: str, name: str) -> bool:
        if not self.settings:
            return False
        custom = _load_json(self.settings.get(key))
        removed = custom.pop(normalize(name), None)
        self._save(key, custom)
        return removed is not None

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
