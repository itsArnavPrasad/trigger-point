"""Runtime settings. Each provider has an explicit live/replay mode, stamped on every run."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

Mode = Literal["live", "replay"]
RunMode = Literal["live", "replay", "mixed"]
PROVIDERS = ("web", "llm", "crustdata")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser for the project .env (comments, quotes, `export` prefix)."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def merge_env(process_env: Mapping[str, str], file_env: Mapping[str, str]) -> dict[str, str]:
    """Secrets (`*_API_KEY`) come from the project .env when it defines them, because stale
    shell exports of placeholder keys are common. Any other setting can be overridden from
    the shell, e.g. `WEB_MODE=replay` for a demo."""
    merged = {**file_env, **process_env}
    merged.update({k: v for k, v in file_env.items() if k.endswith("_API_KEY") and v})
    return merged


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def _mode(env: Mapping[str, str], name: str) -> Mode:
    raw = (env.get(name) or "replay").strip().lower()
    if raw == "live":
        return "live"
    if raw == "replay":
        return "replay"
    raise ConfigError(f"{name} must be 'live' or 'replay', got {raw!r}")


def _secret(env: Mapping[str, str], name: str) -> SecretStr | None:
    raw = (env.get(name) or "").strip()
    return SecretStr(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    provider_modes: dict[str, Mode]
    database_path: str
    fixtures_dir: str
    llm_model: str
    hyde_base_url: str
    hyde_api_key: SecretStr | None = field(repr=False)
    crustdata_api_key: SecretStr | None = field(repr=False)
    crustdata_api_version: str = "2025-11-01"
    crustdata_run_credit_budget: float = 5.0
    crustdata_fetch_contacts: bool = False  # buy email and phone for the buyers found (live only)
    enable_email_send: bool = False
    enable_linkedin_send: bool = False
    test_recipients: tuple[str, ...] = ()  # the only inboxes a test send may reach
    outreach_mode: Literal["demo", "live"] = "demo"  # demo: every send goes to a test inbox
    autopilot_default: bool = True  # new missions start on Autopilot

    @property
    def run_mode(self) -> RunMode:
        modes = set(self.provider_modes.values())
        if modes == {"live"}:
            return "live"
        return "replay" if modes == {"replay"} else "mixed"

    @property
    def replay_providers(self) -> list[str]:
        return [p for p in PROVIDERS if self.provider_modes[p] == "replay"]


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        env = merge_env(os.environ, read_env_file(PROJECT_ROOT / ".env"))

    modes: dict[str, Mode] = {p: _mode(env, f"{p.upper()}_MODE") for p in PROVIDERS}
    hyde_key = _secret(env, "HYDE_INFERENCE_API_KEY")
    crustdata_key = _secret(env, "CRUSTDATA_API_KEY")
    if modes["llm"] == "live" and hyde_key is None:
        raise ConfigError("LLM_MODE=live requires HYDE_INFERENCE_API_KEY")
    if modes["crustdata"] == "live" and crustdata_key is None:
        raise ConfigError("CRUSTDATA_MODE=live requires CRUSTDATA_API_KEY")

    # The MVP prepares and verifies campaigns; it never sends. Refuse rather than ignore.
    outreach_mode = (env.get("OUTREACH_MODE") or "demo").strip().lower()
    if outreach_mode not in ("demo", "live"):
        raise ConfigError(f"OUTREACH_MODE must be 'demo' or 'live', got {outreach_mode!r}")
    if _flag(env, "ENABLE_LINKEDIN_SEND", False):
        raise ConfigError("ENABLE_LINKEDIN_SEND=true is not supported: LinkedIn send is disabled")
    if _flag(env, "ENABLE_EMAIL_SEND", False) and outreach_mode != "live":
        raise ConfigError(
            "ENABLE_EMAIL_SEND=true needs OUTREACH_MODE=live: send stays disabled in demo"
        )
    if outreach_mode == "live" and not _flag(env, "ENABLE_EMAIL_SEND", False):
        raise ConfigError("OUTREACH_MODE=live requires ENABLE_EMAIL_SEND=true")

    all_replay = set(modes.values()) == {"replay"}
    # Separate default databases keep pure-replay records out of live history.
    default_db = (
        "sqlite:///./trigger_point-replay.db" if all_replay else "sqlite:///./trigger_point.db"
    )
    database_url = env.get("DATABASE_URL") or default_db
    if not database_url.startswith("sqlite:///"):
        raise ConfigError("only sqlite:/// DATABASE_URL is supported in the MVP")
    try:
        budget = float(env.get("CRUSTDATA_RUN_CREDIT_BUDGET") or 5.0)
    except ValueError as exc:
        raise ConfigError("CRUSTDATA_RUN_CREDIT_BUDGET must be a number") from exc

    return Settings(
        provider_modes=modes,
        database_path=database_url.removeprefix("sqlite:///"),
        fixtures_dir=env.get(
            "TRIGGER_POINT_FIXTURES_DIR", str(PROJECT_ROOT / "fixtures" / "replay")
        ),
        llm_model=env.get("LLM_MODEL") or "hyde/glm-5.3-flash",
        hyde_base_url=(env.get("HYDE_BASE_URL") or "https://inference.hyde.tech/v1").rstrip("/"),
        hyde_api_key=hyde_key,
        crustdata_api_key=crustdata_key,
        crustdata_api_version=env.get("CRUSTDATA_API_VERSION") or "2025-11-01",
        crustdata_run_credit_budget=budget,
        crustdata_fetch_contacts=(
            modes["crustdata"] == "live"
            and (env.get("CRUSTDATA_FETCH_CONTACTS") or "true").strip().lower()
            not in ("0", "false", "no", "off")
        ),
        outreach_mode="live" if outreach_mode == "live" else "demo",
        autopilot_default=_flag(env, "AUTOPILOT_DEFAULT", True),
        enable_email_send=outreach_mode == "live",
        test_recipients=tuple(
            r.strip().casefold()
            for r in (env.get("TRIGGER_POINT_TEST_RECIPIENTS") or "").split(",")
            if r.strip()
        ),
    )
