# view-cue 시스템 아키텍처

## 개요

면접 영상을 수신해 분석하고, LLM으로 피드백 리포트를 생성하는 FastAPI 백엔드 서버.
프론트엔드(Expo/React Native 앱)는 별도로 구현 완료된 상태이며, 이 저장소의 범위는 FastAPI 서버 전체다.

## 핵심 설계 원칙

> **"Python이 숫자 지표를 만들고, LLM이 그 지표를 해석한다."**

- LLM API는 영상 자체를 분석하지 않는다. 질문, STT 답변 텍스트, 이력서/JD 요약, Python 서버가 산출한 metrics JSON만 입력받는다.
- 파인튜닝은 사용하지 않는다. 필요한 것은 모델 학습이 아니라 **지표 산출 기준과 임계값 튜닝**이다.
- 시선 분석은 정밀 눈동자 추적이 아니라 얼굴 방향·위치 기반의 **"정면 응시 추정"**을 MVP 기준으로 삼는다.

## 시스템 구성

```
[Expo/RN 앱]
    │  ① 이력서/JD 등록, 세션 생성, 답변 영상 업로드(multipart), 상태 폴링
    ▼
[FastAPI 서버 (view-cue)]
    │
    ├─ ffmpeg ──────── 영상 → 오디오(wav) + 프레임 분리
    ├─ silero-vad ──── 발화/침묵 구간 검출 (침묵 지표 + STT 입력 선별)
    ├─ OpenAI whisper-1 ─ 발화 구간 → 한국어 transcript (STT, word timestamps)
    ├─ librosa·parselmouth ─ 오디오 지표 산출 (AudioMetrics)
    ├─ OpenCV + MediaPipe Face Landmarker ─ 영상 지표 산출 (VideoMetrics)
    ├─ OpenAI GPT ──── 질문+transcript+이력서/JD요약+metrics → 피드백/리포트
    │
    ▼
[Supabase]
    ├─ Postgres: 사용자, 세션, 질문, 답변(transcript·metrics·피드백), 리포트, 잡 상태
    └─ Storage: 업로드 영상 (단기 보관 후 삭제)
```

## 답변 분석 파이프라인 (`app/services/pipeline.py`)

1. **수신**: `POST /sessions/{id}/answers`로 영상 multipart 수신 → 임시 디렉터리 저장, `answers.status = processing`, 202 응답
2. **분리**: ffmpeg로 오디오(16kHz mono wav)와 프레임(샘플링) 추출
3. **분석** (오디오/영상 트랙은 병렬 가능, 오디오 트랙 내부는 순차):
   - VAD: silero-vad(ONNX, torch 불필요)로 발화/침묵 구간 검출 → 침묵·멈춤 지표 + STT에 투입할 발화 구간 선별 (Whisper 무음 환각 방지 + 비용 절감)
   - STT: whisper-1 고정 (word-level 타임스탬프는 whisper-1만 지원 — gpt-4o-transcribe 미지원) → transcript. prompt에 한국어 필러 예시를 넣어 필러 보존 유도
   - 오디오 지표: STT 타임스탬프 → 말 빠르기 / transcript 매칭 → 필러 / librosa·parselmouth → 에너지, 음량 변화, 피치 변화, 억양 단조로움
   - 영상 지표: MediaPipe Face Landmarker → 얼굴 감지율, 중앙 유지율, 고개 이탈, 정면 응시 추정, 미검출 시간
4. **저장**: transcript + metrics JSON을 `answers`에 저장
5. **해석**: LLM에 질문/transcript/이력서·JD 요약/metrics 입력 → 5축 점수, good/fix 코멘트, 개선 답변, 꼬리질문 생성·저장
6. **정리**: 임시 오디오·프레임 즉시 삭제, 원본 영상은 보관 정책(`VIDEO_RETENTION_HOURS`)에 따라 삭제 또는 단기 보관
7. **완료**: `answers.status = done` (실패 시 `failed` + 오류 기록)

비동기 실행은 MVP에서 FastAPI BackgroundTasks를 사용하되, CPU-bound 분석(MediaPipe·librosa·parselmouth 등)은
`app/core/jobs.py`의 ProcessPoolExecutor 실행기로 격리한다 — GIL로 인한 이벤트 루프(헬스체크·폴링 응답) 블로킹 방지.
잡 상태를 DB에 기록하고 jobs.py 추상화 뒤에 실행 방식을 숨겨 추후 Celery/ARQ 등 큐로 교체할 수 있게 한다.

## metrics JSON 정의 (`app/schemas/metrics.py`)

| 그룹 | 필드 | 의미 | 산출 도구 |
|------|------|------|----------|
| 공통 | `duration_seconds` | 답변 길이(초) | ffmpeg |
| audio | `speech_rate_wpm` | 말 빠르기 (분당 단어/어절 수) | STT(whisper-1) word 타임스탬프 |
| audio | `silent_seconds` | 총 침묵 시간(초) | silero-vad |
| audio | `pause_count` | 일정 길이 이상 멈춤 횟수 | silero-vad |
| audio | `filler_count` | 필러 단어 수 ("음", "어", "그") — 근사치 (Whisper 필러 정규화 경향) | transcript 매칭 |
| audio | `pitch_variation` | 피치 변화 (F0 표준편차) | parselmouth |
| audio | `energy_mean` | 평균 발화 에너지 (RMS) | librosa |
| audio | `volume_variation` | 음량 변화 | librosa |
| audio | `intonation_monotony` | 억양 단조로움 (낮을수록 단조) | parselmouth |
| video | `face_visible_ratio` | 얼굴 감지율 (0~1) | MediaPipe |
| video | `face_center_ratio` | 얼굴 중앙 유지율 (0~1) | MediaPipe |
| video | `front_face_ratio` | 정면 응시 추정 비율 (0~1) | MediaPipe (head pose) |
| video | `head_turn_count` | 고개 좌우 이탈 횟수 | MediaPipe (yaw) |
| video | `head_nod_count` | 고개 상하 이탈 횟수 | MediaPipe (pitch) |
| video | `face_lost_seconds` | 얼굴 미검출 시간(초) | MediaPipe |

지표 정의·임계값은 Phase 8에서 튜닝한다. 필드 추가 시 이 문서와 `app/schemas/metrics.py`, `docs/api/api-spec.md`를 함께 갱신한다.

## LLM의 역할 (입력/출력 계약)

| 용도 | 입력 | 출력 |
|------|------|------|
| 이력서 파싱 | 이력서 텍스트 | `{name, role, years, skills[], highlights[]}` |
| JD 파싱 | 공고 텍스트/URL 본문 | `{company, role, type, source, must[], nice[]}` |
| 적합도·질문 생성 | 이력서 요약 + JD 요약 | 적합도 `{score, matched[]}` + 질문 8개 `{cat, text, limit, why}` |
| 답변 피드백 | 질문 + transcript + 이력서/JD 요약 + metrics JSON | 5축 점수 `{content, star, voice, gaze, delivery}`, good/fix, 개선 답변, 꼬리질문 |
| 종합 리포트 | 세션 전체 답변 피드백 + 평균 지표 | 종합 점수, top 개선점, 심층 분석 요약 |

모든 LLM 호출은 구조화 출력(JSON Schema)을 강제한다.

## 데이터 저장 (Supabase)

| 테이블 | 내용 |
|--------|------|
| `profiles` | 사용자 (Supabase Auth 연동) |
| `resumes` | 이력서 원문 + 파싱 결과(JSONB) |
| `job_postings` | 채용공고 원문 + 파싱 결과(JSONB) |
| `interview_sessions` | 세션 (resume/job 참조, 상태, 적합도 결과, 종합 점수) |
| `questions` | 세션별 생성 질문 (카테고리, 본문, 권장시간, 의도) |
| `answers` | 질문별 답변 (영상 경로, 잡 상태, transcript, metrics JSONB, 피드백 JSONB, retry_of) |
| `reports` | 세션 종합 리포트 (JSONB) |

스키마 상세는 Phase 1에서 확정한다 (`docs/plan/implementation-plan.md`).

## 파일 수명주기

- **임시 오디오·프레임**: 분석 완료 즉시 삭제
- **원본 영상**: Supabase Storage에 업로드 후 `VIDEO_RETENTION_HOURS`(기본 24h) 경과 시 삭제 — 정리 배치는 Phase 8
- **transcript·metrics·리포트**: Postgres에 영구 보관 (재도전 비교, 허브 목록의 근거 데이터)
