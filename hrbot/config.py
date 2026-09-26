"""Configuration is intentionally small and keeps credentials out of source control."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    allowed_numbers: tuple[str, ...]
    sheet_id: str
    service_account_file: Path
    whisper_model: str
    ollama_url: str
    ollama_model: str
    timezone: ZoneInfo
    poll_seconds: int
    db_file: Path
    data_dir: Path
    chrome_profile: Path
    supervisors: dict[str, str]
    field_aliases: dict[str, str]


def load_settings() -> Settings:
    load_env()
    path = ROOT / "config.json"
    if not path.exists():
        path = ROOT / "config.example.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    numbers = tuple("".join(c for c in number if c.isdigit()) for number in os.getenv("WHATSAPP_ALLOWED_NUMBERS", "").split(","))
    numbers = tuple(number for number in numbers if number)
    data_dir = ROOT / "data"
    return Settings(
        allowed_numbers=numbers,
        sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
        service_account_file=ROOT / os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json"),
        whisper_model=os.getenv("WHISPER_MODEL", "small"),
        ollama_url=os.getenv("OLLAMA_URL", "").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", ""),
        timezone=ZoneInfo(os.getenv("TIMEZONE", "Asia/Karachi")),
        poll_seconds=max(3, int(os.getenv("POLL_SECONDS", "8"))),
        db_file=data_dir / "hrbot-live.sqlite3",
        data_dir=data_dir,
        chrome_profile=ROOT / "chrome-profile",
        supervisors=config["supervisors"],
        field_aliases={key.casefold(): value for key, value in config["field_aliases"].items()},
    )
