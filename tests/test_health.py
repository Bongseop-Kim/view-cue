"""헬스 체크 + 분석 라이브러리 호환성 스모크 테스트."""

import importlib

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "module",
    [
        "cv2",
        "mediapipe",
        "librosa",
        "parselmouth",
        "webrtcvad",
        "soundfile",
        "openai",
        "supabase",
    ],
)
def test_analysis_dependencies_importable(module: str) -> None:
    importlib.import_module(module)
