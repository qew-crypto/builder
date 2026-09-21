from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Заполните {name} в файле .env")
    return value


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_ids: frozenset[int]
    data_dir: Path
    uploads_dir: Path
    database_path: Path
    fernet_key: str | None
    max_archive_mb: int
    delete_repo_after_build: bool


def load_settings() -> Settings:
    try:
        ids = frozenset(int(x.strip()) for x in required("ALLOWED_TELEGRAM_IDS").split(",") if x.strip())
    except ValueError as exc:
        raise RuntimeError("ALLOWED_TELEGRAM_IDS должен содержать цифровые ID через запятую") from exc
    data = Path(os.getenv("DATA_DIR", "data")).resolve()
    uploads = data / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return Settings(
        telegram_token=required("TELEGRAM_BOT_TOKEN"),
        allowed_ids=ids,
        data_dir=data,
        uploads_dir=uploads,
        database_path=data / "bot.sqlite3",
        fernet_key=os.getenv("FERNET_KEY", "").strip() or None,
        max_archive_mb=int(os.getenv("MAX_ARCHIVE_MB", "45")),
        delete_repo_after_build=os.getenv("DELETE_REPO_AFTER_BUILD", "false").lower() == "true",
    )
