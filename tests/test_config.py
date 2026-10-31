from pathlib import Path

import pytest

from trigger_point.config import ConfigError, load_settings, read_env_file

HYDE = {"HYDE_INFERENCE_API_KEY": "sk-hyde-secret"}


def test_defaults_to_replay_for_every_provider_with_sends_disabled() -> None:
    s = load_settings({})
    assert s.provider_modes == {"web": "replay", "llm": "replay", "crustdata": "replay"}
    assert s.run_mode == "replay"
    assert s.enable_email_send is False and s.enable_linkedin_send is False


def test_mixed_modes() -> None:
    s = load_settings({"WEB_MODE": "live", "LLM_MODE": "live", **HYDE})
    assert s.provider_modes == {"web": "live", "llm": "live", "crustdata": "replay"}
    assert s.run_mode == "mixed"
    assert s.replay_providers == ["crustdata"]


def test_live_llm_requires_provider_key() -> None:
    with pytest.raises(ConfigError, match="HYDE_INFERENCE_API_KEY"):
        load_settings({"LLM_MODE": "live"})


def test_live_crustdata_requires_key() -> None:
    with pytest.raises(ConfigError, match="CRUSTDATA_API_KEY"):
        load_settings({"CRUSTDATA_MODE": "live"})


def test_invalid_mode_value() -> None:
    with pytest.raises(ConfigError, match="WEB_MODE"):
        load_settings({"WEB_MODE": "sometimes"})


def test_hyde_defaults() -> None:
    s = load_settings({"LLM_MODE": "live", **HYDE})
    assert s.llm_model == "hyde/glm-5.3-flash"
    assert s.hyde_base_url == "https://inference.hyde.tech/v1"


def test_secret_values_never_in_repr() -> None:
    s = load_settings({"CRUSTDATA_API_KEY": "cd-secret-value", **HYDE})
    assert "cd-secret-value" not in repr(s) and "sk-hyde-secret" not in repr(s)


def test_sends_cannot_be_enabled_in_mvp() -> None:
    with pytest.raises(ConfigError, match="send"):
        load_settings({"ENABLE_EMAIL_SEND": "true"})


def test_default_database_is_separate_for_pure_replay() -> None:
    assert load_settings({}).database_path.endswith("trigger_point-replay.db")
    live = load_settings({"WEB_MODE": "live"}).database_path
    assert live.endswith("trigger_point.db") and not live.endswith("replay.db")


def test_read_env_file(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("# comment\n\nA=1\nB = \"two words\"\nC='x=y'\nexport D=4\nBROKEN\n")
    assert read_env_file(f) == {"A": "1", "B": "two words", "C": "x=y", "D": "4"}
    assert read_env_file(tmp_path / "missing") == {}


def test_env_file_secrets_beat_stale_shell_exports_but_shell_overrides_settings() -> None:
    from trigger_point.config import merge_env

    merged = merge_env(
        {"HYDE_INFERENCE_API_KEY": "sk-placeholder", "WEB_MODE": "replay", "PATH": "/bin"},
        {"HYDE_INFERENCE_API_KEY": "sk-real", "WEB_MODE": "live", "LLM_MODE": "live"},
    )
    assert merged["HYDE_INFERENCE_API_KEY"] == "sk-real"  # secrets: .env wins
    assert merged["WEB_MODE"] == "replay"  # settings: the shell can override for a demo
    assert merged["LLM_MODE"] == "live" and merged["PATH"] == "/bin"
