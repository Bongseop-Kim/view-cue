"""분석 지표 (metrics JSON) Pydantic 스키마.

"Python이 숫자 지표를 만들고, LLM이 그 지표를 해석한다" — 이 모듈의 모델이
오디오/영상 분석 결과와 LLM 입력 사이의 계약(contract)이 된다.
필드 정의는 docs/api/api-spec.md의 metrics JSON 명세와 동기화한다.
"""

from pydantic import BaseModel


class AudioMetrics(BaseModel):
    """오디오 분석 지표 (VAD·librosa·parselmouth 산출)."""

    speech_rate_wpm: float | None = None
    silent_seconds: float | None = None
    pause_count: int | None = None
    filler_count: int | None = None
    pitch_variation: float | None = None
    energy_mean: float | None = None
    volume_variation: float | None = None
    intonation_monotony: float | None = None


class VideoMetrics(BaseModel):
    """영상 프레임 분석 지표 (OpenCV + MediaPipe Face Landmarker 산출)."""

    face_visible_ratio: float | None = None
    face_center_ratio: float | None = None
    front_face_ratio: float | None = None
    head_turn_count: int | None = None
    head_nod_count: int | None = None
    face_lost_seconds: float | None = None


class AnswerMetrics(BaseModel):
    """답변 1건의 전체 지표 묶음 (answers.metrics JSONB로 저장)."""

    duration_seconds: float | None = None
    audio: AudioMetrics = AudioMetrics()
    video: VideoMetrics = VideoMetrics()
