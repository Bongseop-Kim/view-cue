# view-cue

면접 영상을 수신해 분석하고, LLM으로 피드백 리포트를 생성하는 FastAPI 백엔드 서버.

핵심 원칙: **"Python이 숫자 지표를 만들고, LLM이 그 지표를 해석한다."**
파인튜닝 없이, 지표 산출 기준과 임계값 튜닝으로 품질을 관리한다.

## 기술 스택

- **서버**: FastAPI + Uvicorn (Python 3.12, uv)
- **영상/오디오 분리**: ffmpeg
- **STT**: OpenAI Whisper API (한국어)
- **오디오 지표**: VAD(webrtcvad) · librosa · parselmouth
- **영상 지표**: OpenCV + MediaPipe Face Landmarker
- **LLM 리포트**: OpenAI GPT
- **저장소**: Supabase (Postgres + Storage)
- **비동기 분석**: FastAPI BackgroundTasks (MVP, 추후 큐 교체 가능)

## 사전 요구사항

```bash
# uv (Python 패키지 관리)
curl -LsSf https://astral.sh/uv/install.sh | sh

# ffmpeg (시스템 의존성 — 영상에서 오디오/프레임 분리)
brew install ffmpeg
```

## 시작하기

```bash
uv sync                          # 의존성 설치 (Python 3.12 자동 다운로드)
cp .env.example .env             # 환경 변수 설정 (API 키 입력)
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

- 헬스 체크: `GET /health`
- API 문서(Swagger): http://localhost:8000/docs

## 개발 명령어

```bash
uv run pytest          # 테스트
uv run ruff check .    # 린트
uv run ruff format .   # 포맷
```

## 문서

| 문서 | 내용 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 시스템 아키텍처, 분석 파이프라인, metrics JSON 정의 |
| [docs/api/api-spec.md](docs/api/api-spec.md) | API 명세서 (프론트엔드 화면 플로우 기반) |
| [docs/plan/implementation-plan.md](docs/plan/implementation-plan.md) | 단계별 구현 계획 (Phase 1~8) |

## 프로젝트 구조

```
app/
├── main.py            # FastAPI 앱 엔트리포인트
├── config.py          # 환경 변수 설정 (pydantic-settings)
├── api/routes/        # API 라우터 (health, resumes, job_postings, sessions, answers, reports)
├── schemas/           # Pydantic 모델 (metrics JSON 계약 포함)
├── services/          # 분석 서비스 (stt, audio_metrics, video_metrics, llm_report, pipeline)
├── clients/           # 외부 클라이언트 (OpenAI, Supabase)
└── core/              # 백그라운드 잡 추상화
```
