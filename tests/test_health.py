from pathlib import Path

from fastapi.testclient import TestClient

from trigger_point.api.app import create_app
from trigger_point.config import load_settings


def test_health_reports_mode(tmp_path: Path) -> None:
    settings = load_settings({"DATABASE_URL": f"sqlite:///{tmp_path / 't.db'}"})
    client = TestClient(create_app(settings))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "mode": "replay",
        "web_mode": "replay",
        "llm_mode": "replay",
        "crustdata_mode": "replay",
    }
