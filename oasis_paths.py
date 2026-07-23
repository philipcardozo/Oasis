"""Cross-platform filesystem defaults.

Precedence (highest first):
  1. explicit argument passed by the caller
  2. environment variable
  3. config file  (OASIS_CONFIG, or <app data>/config.json)
  4. platform application-data directory
  5. repository-local development fallback (only when OASIS_DEV=1 or the repo
     directory already exists — never invented on an end-user machine)

Platform application-data directories:
  macOS    ~/Library/Application Support/OASIS
  Windows  %LOCALAPPDATA%\\OASIS
  Linux    $XDG_DATA_HOME/oasis  (else ~/.local/share/oasis)

Never assumes a writable filesystem root, POSIX separators, case sensitivity,
symlinks, or elevated privileges. Directories are created only on demand.
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "OASIS"


def app_data_dir() -> Path:
    """Platform-appropriate per-user application data directory."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / APP_NAME if base else Path.home() / "AppData" / "Local" / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) / "oasis" if xdg else Path.home() / ".local" / "share" / "oasis"


@lru_cache(maxsize=1)
def _config() -> dict:
    explicit = os.environ.get("OASIS_CONFIG")
    for candidate in ([Path(explicit)] if explicit else []) + [app_data_dir() / "config.json"]:
        try:
            if candidate.is_file():
                return json.loads(candidate.read_text("utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def _dev_mode() -> bool:
    return os.environ.get("OASIS_DEV", "").strip().lower() in {"1", "true", "yes"}


def resolve_dir(
    key: str,
    env_var: str,
    *,
    explicit: str | os.PathLike | None = None,
    repo_relative: str | None = None,
    app_relative: str | None = None,
) -> Path:
    """Resolve a directory following the documented precedence. Does not create it."""
    if explicit:
        return Path(explicit).expanduser()

    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return Path(env_value).expanduser()

    cfg = _config().get(key)
    if cfg:
        return Path(str(cfg)).expanduser()

    # Repo-local fallback: only in dev mode, or when the repo path already exists
    # (keeps existing local caches working without relocating them).
    if repo_relative:
        repo_path = ROOT / repo_relative
        if _dev_mode() or repo_path.exists():
            return repo_path

    return app_data_dir() / (app_relative or key)


def ensure_dir(path: Path) -> Path:
    """Create a directory on demand with an actionable error if storage is unusable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(
            f"cannot create OASIS directory {path}: {exc}. "
            f"Set a writable location via the matching OASIS_* environment variable."
        ) from exc
    return path


def raw_data_root(explicit: str | os.PathLike | None = None) -> Path:
    """Ingestion source data. Replaces the old POSIX-only '/data/raw' default."""
    return resolve_dir("raw_data_root", "OASIS_RAW_DATA_ROOT",
                       explicit=explicit, repo_relative="data/raw", app_relative="raw")


def facts_dir(explicit: str | os.PathLike | None = None) -> Path:
    """SEC companyfacts cache."""
    return resolve_dir("facts_dir", "OASIS_FACTS_DIR",
                       explicit=explicit, repo_relative="graph/data/companyfacts",
                       app_relative="companyfacts")


if __name__ == "__main__":
    print(f"platform          {sys.platform} (os.name={os.name})")
    print(f"app_data_dir      {app_data_dir()}")
    print(f"raw_data_root     {raw_data_root()}")
    print(f"facts_dir         {facts_dir()}")
