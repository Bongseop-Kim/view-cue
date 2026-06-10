# view-cue 구현 계획 (초기 세팅 이후)

초기 프로젝트 세팅(Phase 0, 완료) 이후 실행할 단계별 구현 계획.
각 Phase는 독립적으로 검증 가능한 단위로 나누었고, 순서대로 진행하면 프론트엔드 6단계 플로우가 끝에서 완성된다.

참고 문서:
- 아키텍처·지표 정의: `docs/architecture.md`
- API 계약: `docs/api/api-spec.md`

---

## Phase 0 — 초기 세팅 ✅ (완료)

uv + Python 3.12, FastAPI 골격(`app/`), 의존성(mediapipe·librosa·parselmouth 포함) 설치 검증,
`/health`, 문서 3종, import 스모크 테스트.

---

## Phase 1 — Supabase 스키마 & 연동

**목표**: 데이터 저장 기반과 인증 검증을 갖춘다.

**작업**:
- 테이블 생성 (마이그레이션 SQL은 `supabase/migrations/`에 관리):
  - `profiles` (Supabase Auth `auth.users` 연동)
  - `resumes` (user_id, source_type, raw_text, parsed JSONB, file_name)
  - `job_postings` (동일 구조)
  - `interview_sessions` (user_id, resume_id, job_posting_id, status, match JSONB, overall_score)
  - `questions` (session_id, order, cat, text, limit_seconds, why)
  - `answers` (session_id, question_id, retry_of, status, video_path, duration_seconds, transcript, metrics JSONB, feedback JSONB, error JSONB)
  - `reports` (session_id, status, payload JSONB)
- Storage 버킷 `interview-videos` 생성 (private)
- RLS 정책: 본인 데이터만 접근
- `app/clients/supabase_client.py` 구현 (service role 클라이언트)
- JWT 검증 의존성 (`Authorization: Bearer` → user_id 추출) — FastAPI Depends
- 리소스별 기본 CRUD 헬퍼

**검증**: 로컬에서 테이블 생성 확인, JWT로 보호된 더미 엔드포인트 401/200 동작, RLS로 타 사용자 데이터 차단 확인.

---

## Phase 2 — 이력서/JD 등록·파싱 + 적합도·질문 생성 (Step 1~3)

**목표**: 텍스트 입력만으로 면접 준비 플로우(Step 1→3)가 동작한다. BackgroundTasks 잡 패턴을 여기서 확립한다.

**작업**:
- `POST /resumes`, `POST /job-postings`: 텍스트 입력 → LLM 구조화 파싱 (파일 업로드는 PDF 텍스트 추출 포함 — pypdf 추가)
- `app/clients/openai_client.py` + LLM 호출 공통 모듈 (JSON Schema 구조화 출력, 재시도)
- `POST /sessions`: 202 + BackgroundTasks로 적합도 매칭 + 질문 8개 생성 → `interview_sessions.match`, `questions` 저장
- `app/core/jobs.py`: 잡 실행 + DB 상태 기록 추상화 (pending/processing/done/failed) — 이후 Phase에서 재사용
- `GET /sessions/{id}` 폴링, `GET /sessions` 목록

**검증**: 실제 이력서/공고 텍스트로 end-to-end 호출 → 질문 8개가 카테고리(오프닝/지원동기/경험/관계/직무/인성/가치) 분포로 생성되는지, 폴링 상태 전이(analyzing→ready) 확인. 단위 테스트는 LLM 모킹.

---

## Phase 3 — 영상 업로드 파이프라인 (ffmpeg)

**목표**: 영상을 받아 분석 가능한 산출물(오디오·프레임)로 분리하고 파일 수명주기를 관리한다.

**작업**:
- `POST /sessions/{id}/answers`: multipart 수신 (크기/형식 검증), `answers` 행 생성(status=processing), 202
- ffmpeg 래퍼: 영상 → 16kHz mono wav + 프레임 샘플링(예: 5fps) — subprocess 기반, 타임아웃 처리
- Supabase Storage 업로드 (원본 영상), 임시 디렉터리 관리 (`TEMP_DIR`)
- 분석 완료/실패 시 임시 파일 즉시 삭제
- `GET /answers/{id}` 폴링 (이 시점에는 transcript/metrics 없이 상태만)

**검증**: 샘플 영상 업로드 → wav/프레임 생성 확인, 실패 케이스(손상 파일, 오디오 없음)에서 status=failed + 임시 파일 잔존 없음 확인.

---

## Phase 4 — 오디오 분석 (STT + 음성 지표)

**목표**: `AudioMetrics` 전체 필드를 실제 값으로 산출한다.

**작업**:
- `app/services/stt.py`: Whisper API 호출 (한국어, 단어/세그먼트 타임스탬프 요청), transcript 저장
- `app/services/audio_metrics.py`:
  - webrtcvad: 발화/침묵 구간 → `silent_seconds`, `pause_count`
  - STT 타임스탬프 + 어절 수 → `speech_rate_wpm`
  - transcript 필러 매칭("음", "어", "그", "약간" 등 사전 기반) → `filler_count`
  - librosa: RMS → `energy_mean`, `volume_variation`
  - parselmouth: F0 추출 → `pitch_variation`, `intonation_monotony`
- 파이프라인에 결합, `answers.metrics.audio` 저장
- (옵션 검토) silero-vad로 교체 — webrtcvad 정확도가 부족할 경우. torch 의존 비용 고려.

**검증**: 특성이 다른 샘플 오디오(빠른 발화/느린 발화/침묵 많은) 3개 이상으로 지표 방향성 확인 — 빠른 발화에서 wpm↑, 침묵 많은 샘플에서 silent_seconds↑. pytest로 산출 함수 단위 테스트.

---

## Phase 5 — 영상 분석 (MediaPipe 지표)

**목표**: `VideoMetrics` 전체 필드를 실제 값으로 산출한다.

**작업**:
- MediaPipe Face Landmarker 모델(.task) 다운로드 스크립트/경로 관리
- `app/services/video_metrics.py`:
  - 프레임별 얼굴 검출 → `face_visible_ratio`, `face_lost_seconds`
  - 얼굴 bounding box 중심 vs 프레임 중심 → `face_center_ratio`
  - facial transformation matrix로 head pose(yaw/pitch) 추정 → `front_face_ratio` (yaw·pitch 임계값 이내 비율), `head_turn_count`, `head_nod_count` (임계값 초과 이벤트 카운트)
- 파이프라인 결합, `answers.metrics.video` 저장
- 임계값은 상수 모듈로 분리 (Phase 8 튜닝 대상)

**검증**: 정면 응시 영상 vs 시선 이탈 많은 영상으로 지표 방향성 확인 (front_face_ratio 차이). 프레임 처리 속도 측정 (1분 영상 기준 처리 시간 기록).

---

## Phase 6 — LLM 피드백·종합 리포트 (Step 5)

**목표**: 분석 결과를 사용자에게 전달할 피드백으로 변환한다. "LLM이 지표를 해석한다"의 본체.

**작업**:
- 답변 피드백 프롬프트: 질문 + transcript + 이력서/JD 요약 + metrics JSON → 5축 점수, good/fix, 개선 답변, 꼬리질문 (JSON Schema 출력) → `answers.feedback`
- 5축 점수 산출 규칙 문서화: `content`/`star`는 LLM 판단 중심, `voice`/`gaze`/`delivery`는 metrics 기반 가이드(점수 매핑 기준표를 프롬프트에 포함)
- 종합 리포트: `POST/GET /sessions/{id}/report` — 5축 평균, peer 비교(MVP는 고정 기준값 테이블), top_fixes, deep_analysis
- `GET /answers/{id}` 완성 (transcript+metrics+feedback 전체 응답)

**검증**: 실제 답변 영상 1건 end-to-end (업로드→폴링→피드백 확인). 동일 입력 반복 호출 시 점수 편차 측정(±5 이내 목표). LLM 모킹 단위 테스트.

---

## Phase 7 — 재도전·비교 & 허브 (Step 6, 허브 완성)

**목표**: 학습 루프(약점 파악→재도전→개선 확인)를 완성한다.

**작업**:
- `GET /sessions/{id}/weak-questions`: content+star 하위 N개 선정
- `retry_of` 처리: 재답변 업로드 시 동일 파이프라인 + 비교 데이터 연결
- `GET /answers/{id}/comparison`: 이전/이번 점수·transcript·delta + LLM 비교 요약 한 줄
- `GET /sessions` 목록의 `score_delta` (직전 세션 대비) 계산

**검증**: 동일 질문 2회 답변 → comparison 응답의 delta 정합성, 허브 목록 delta 표시 확인.

---

## Phase 8 — 지표 임계값 튜닝 & 운영

**목표**: 점수 품질과 운영 안정성. 파인튜닝이 아니라 **임계값 튜닝**이 이 프로젝트의 품질 작업이다.

**작업**:
- 지표→점수 매핑 기준표 보정: 샘플 영상 셋(좋은 답변/나쁜 답변)으로 5축 점수의 변별력 검증, voice/gaze/delivery 매핑 테이블·head pose 임계값 조정
- peer 기준값 테이블 갱신 체계 (실데이터 누적 시)
- 원본 영상 보관 정책 실행: `VIDEO_RETENTION_HOURS` 경과 영상 삭제 배치 (Supabase cron 또는 서버 스케줄러)
- 에러·재시도: STT/LLM 호출 실패 재시도, 잡 실패 시 부분 결과 보존, 구조화 로깅
- 부하 확인: BackgroundTasks 동시 분석 한계 측정 → 필요 시 큐(Celery/ARQ) 전환 판단 기준 기록

**검증**: 보관 시간 경과 영상 자동 삭제 확인, 의도적 실패 주입(STT 타임아웃 등) 시 failed 상태와 에러 메시지 노출, 동시 업로드 N건 처리 시간 측정.

---

## 범위 외 (현재 결정)

- **실시간 STT 자막** (프로토타입 Step 4 화면에 존재): MVP는 분석 완료 후 transcript 제공. 실시간은 WebSocket + 스트리밍 STT가 필요해 별도 검토.
- **정밀 눈동자(iris) 추적**: 얼굴 방향 기반 "정면 응시 추정"이 MVP 기준.
- **Pro 요금제 노출 제어**: API는 심층 분석을 항상 반환, 잠금은 프론트 책임.
- **파인튜닝**: 사용하지 않음.
