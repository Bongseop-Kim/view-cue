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
  - `profiles` (Supabase Auth `auth.users` 연동, `plan` 컬럼: `free`/`pro` — Pro 노출 제어용)
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
- Pro 권한 확인 의존성 (`profiles.plan` 조회 → free/pro 판별) — Phase 6 deep_analysis 게이팅에서 사용
- 리소스별 기본 CRUD 헬퍼

**검증**: 로컬에서 테이블 생성 확인, JWT로 보호된 더미 엔드포인트 401/200 동작, RLS로 타 사용자 데이터 차단 확인.

---

## Phase 2 — 이력서/JD 등록·파싱 + 적합도·질문 생성 (Step 1~3)

**목표**: 텍스트 입력만으로 면접 준비 플로우(Step 1→3)가 동작한다. BackgroundTasks 잡 패턴을 여기서 확립한다.

**작업**:
- `POST /resumes`, `POST /job-postings`: 텍스트 입력 → LLM 구조화 파싱 (파일 업로드는 PDF 텍스트 추출 포함 — pypdf 추가. 국문 PDF는 CID 폰트·HWP 변환물에서 추출 품질이 흔들릴 수 있어 실측 검증 필수, 미달 시 pdfplumber(MIT)로 전환. PyMuPDF는 CJK에 강하나 AGPL이라 배제)
- `app/clients/openai_client.py` + LLM 호출 공통 모듈 (JSON Schema 구조화 출력, 재시도, temperature=0·seed 고정 옵션 — Phase 6 점수 재현성의 전제)
- `POST /sessions`: 202 + BackgroundTasks로 적합도 매칭 + 질문 8개 생성 → `interview_sessions.match`, `questions` 저장
- `app/core/jobs.py`: 잡 실행 + DB 상태 기록 추상화 (pending/processing/done/failed) — 이후 Phase에서 재사용.
  **CPU-bound 작업(MediaPipe·librosa·parselmouth 등)은 ProcessPoolExecutor로 격리 실행**하는 실행기 인터페이스를 처음부터 포함 — BackgroundTasks 스레드에서 직접 돌리면 GIL로 이벤트 루프(헬스체크·폴링 응답)까지 블로킹됨. 큐 전환(Celery/ARQ) 판단은 Phase 8로 유지하되, 격리는 여기서 해결
- `GET /sessions/{id}` 폴링, `GET /sessions` 목록

**검증**: 실제 이력서/공고 텍스트로 end-to-end 호출 → 질문 8개가 카테고리(오프닝/지원동기/경험/관계/직무/인성/가치) 분포로 생성되는지, 폴링 상태 전이(analyzing→ready) 확인. 실제 국문 이력서 PDF 3종 이상으로 추출 품질 확인. CPU-bound 더미 잡 실행 중에도 `/health` 응답이 막히지 않는지 확인. 단위 테스트는 LLM 모킹.

---

## Phase 3 — 영상 업로드 파이프라인 (ffmpeg)

**목표**: 영상을 받아 분석 가능한 산출물(오디오·프레임)로 분리하고 파일 수명주기를 관리한다.

**작업**:
- `POST /sessions/{id}/answers`: multipart 수신 (크기/형식/길이 검증 — 16kHz mono 16bit wav ≈ 1.9MB/분이므로 Whisper API 25MB 제한 기준 답변 상한 약 13분, `limit_seconds` 대비 충분), `answers` 행 생성(status=processing), 202
- ffmpeg 래퍼: 영상 → 16kHz mono wav + 프레임 샘플링 — subprocess 기반, 타임아웃 처리.
  샘플링 fps: 비율 지표(face_visible/center)는 5fps로 충분하나 **이벤트 카운트(head_turn/nod)는 0.5~1초의 빠른 움직임을 놓칠 수 있어 10fps 이상 필요** — Phase 5에서 "10fps 프레임 추출" vs "MediaPipe VIDEO 모드로 영상 직접 처리(프레임 추출 단계 생략)" 비교 후 확정
- Supabase Storage 업로드 (원본 영상), 임시 디렉터리 관리 (`TEMP_DIR`)
- 분석 완료/실패 시 임시 파일 즉시 삭제
- `GET /answers/{id}` 폴링 (이 시점에는 transcript/metrics 없이 상태만)

**검증**: 샘플 영상 업로드 → wav/프레임 생성 확인, 실패 케이스(손상 파일, 오디오 없음)에서 status=failed + 임시 파일 잔존 없음 확인.

---

## Phase 4 — 오디오 분석 (STT + 음성 지표)

**목표**: `AudioMetrics` 전체 필드를 실제 값으로 산출한다.

**작업**:
- `app/services/vad.py`: **silero-vad (onnxruntime 실행 — torch 불필요)** 로 발화/침묵 구간 산출 → `silent_seconds`, `pause_count`. webrtcvad 대비 정확도가 일관되게 우수해 처음부터 채택
- `app/services/stt.py`: **whisper-1 고정** — word-level 타임스탬프(`timestamp_granularities`)는 whisper-1만 지원, gpt-4o-transcribe는 미지원이라 사용 불가.
  - **VAD 선처리**: 검출된 발화 구간만 STT에 투입 — Whisper의 무음 환각(긴 침묵 시 직전 문장 반복·생성)을 차단하고 비용 절감. 면접 답변은 침묵이 정상 케이스라 필수
  - prompt 파라미터에 한국어 필러("음", "어", "그…")가 포함된 예시 문장 주입 — Whisper는 기본적으로 필러를 정규화·누락하는 경향이 있어 보존을 유도 (보장은 아님)
  - transcript 저장
- `app/services/audio_metrics.py`:
  - STT 타임스탬프 + 어절 수 → `speech_rate_wpm`
  - transcript 필러 매칭("음", "어", "그", "약간" 등 사전 기반) → `filler_count`
  - librosa: RMS → `energy_mean`, `volume_variation`
  - parselmouth: F0 추출 → `pitch_variation`, `intonation_monotony`
- 파이프라인에 결합 (순서: ffmpeg → VAD → STT → 지표), `answers.metrics.audio` 저장

**검증**: 특성이 다른 샘플 오디오(빠른 발화/느린 발화/침묵 많은) 3개 이상으로 지표 방향성 확인 — 빠른 발화에서 wpm↑, 침묵 많은 샘플에서 silent_seconds↑. **필러가 많은 샘플로 filler 검출률(재현율) 측정 — 기준 미달 시 `filler_count`를 보조 지표로 강등하고 한계를 문서화**. 침묵이 긴 샘플에서 환각(없는 문장 생성) 부재 확인. pytest로 산출 함수 단위 테스트. 답변 완료 후 `GET /answers/{id}`의 transcript가 Whisper 결과로 채워지는지 확인.

---

## Phase 5 — 영상 분석 (MediaPipe 지표)

**목표**: `VideoMetrics` 전체 필드를 실제 값으로 산출한다.

**작업**:
- MediaPipe Face Landmarker 모델(.task) 다운로드 스크립트/경로 관리
- 프레임 공급 방식 확정 (Phase 3에서 이연): 10fps 프레임 추출 vs MediaPipe VIDEO 모드 영상 직접 처리 — 이벤트 카운트 정확도와 처리 속도를 비교해 결정
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
- 점수 재현성 확보: temperature=0 + seed 고정(Phase 2 공통 모듈 옵션 사용) + 점수 기준표(루브릭)를 프롬프트에 명시 — ±5 편차 목표의 전제 조건
- 종합 리포트: `POST/GET /sessions/{id}/report` — 5축 평균, peer 비교(MVP는 고정 기준값 테이블), top_fixes, deep_analysis
- Pro 게이팅: `deep_analysis`는 Pro 전용 — 백엔드에서 Supabase `profiles.plan` 확인(Phase 1 의존성 재사용) 후 free 사용자에게는 본문 제외 + `locked: true` 응답. 프론트 노출 제어와 별개로 백엔드가 최종 방어선.
- `GET /answers/{id}` 완성 (transcript+metrics+feedback 전체 응답)

**검증**: 실제 답변 영상 1건 end-to-end (업로드→폴링→피드백 확인). 동일 입력 반복 호출 시 점수 편차 측정(±5 이내 목표). LLM 모킹 단위 테스트. free/pro 계정 각각으로 리포트 호출 → deep_analysis 잠금/노출 확인.

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

## Phase 9 — RAG 기반 질문 품질·peer 기준값 강화 (NCS + AI Hub)

**목표**: 질문 생성이 일반론으로 흐르는 문제와 peer 비교의 고정 기준값 한계를 공개 데이터 RAG로 개선한다.

**작업**:
- 공통 RAG 인프라: Supabase pgvector 확장 활성화 + OpenAI embeddings(text-embedding-3-small) 기반 임베딩·검색 모듈 (`app/services/rag.py`) — 별도 벡터 DB 없음
- **NCS 직무 역량 RAG** (난이도 하, 선행):
  - 공공데이터포털 NCS 기준정보·관련 정보 API로 직무 분류(대/중/소/세분류) + 능력단위 + 수행준거 배치 수집 → 능력단위 단위로 임베딩 저장
  - 직무 명칭 표준은 NCS를 따른다: JD 파싱 시 직무를 NCS 세분류로 정규화(`ncs_code` 저장) — LLM에 NCS 세분류 후보 목록을 주고 분류시키는 매핑 단계 추가 (예: "백엔드 개발자" → "응용SW엔지니어링"). 현업 용어는 표시용으로만 유지
  - Phase 2 질문 생성 직전, 정규화된 NCS 세분류로 능력단위 조회(코드 기반 직접 조회, 임베딩 검색은 보조) → 질문 생성 프롬프트에 "직무 요구 역량" 컨텍스트로 주입
  - 핵심 검증 지점: JD 직무명 → NCS 세분류 매핑 정확도
- **AI Hub 채용면접 인터뷰 데이터 활용** (dataSetSn=71592, 라벨링 텍스트 84k건):
  - 데이터 사용 신청·다운로드 후 전처리: 질문/답변 텍스트 추출, 직업군 분류, 품질 필터링·중복 제거 (음성 데이터는 제외)
  - 질문 은행: 직업군별 실제 질문 임베딩 → 질문 생성 시 few-shot 참고용으로 검색·주입
  - peer 기준값: 직업군별 답변 통계(어절수 분포 등) 집계 배치 → Phase 6 리포트의 고정 기준값 테이블을 실데이터 기반으로 대체
- 라이선스 준수 (구현 제약):
  - 데이터셋 원문(질문/답변 텍스트)을 사용자에게 **그대로 노출 금지** (제3자 열람·제공 금지 조항) — few-shot 주입·통계 집계 등 비노출 방식만 사용
  - NIA(한국지능정보사회진흥원) 사업결과 출처 표기 — 서비스 내 고지

**검증**: 동일 JD로 RAG 적용 전/후 질문 생성 비교 — 직무 특화도 개선 확인(블라인드 평가). NCS 검색이 무관한 직무를 반환하는 비율 측정. peer 기준값 적용 후 리포트 percentile 분포의 타당성 확인. 생성 질문에 데이터셋 원문이 그대로 포함되지 않는지 샘플 검사.

---

## 프롬프트 단위 작업 분해 (실행 순서)

1 프롬프트 = 1 PR 크기 = 독립 검증 가능 단위. Phase는 검증 묶음, 아래가 실제 작업지시 단위다.

| # | 작업지시 | 완료 기준 | 의존 |
|---|---|---|---|
| P1 | Supabase 마이그레이션 SQL: 테이블 7종 + RLS + `interview-videos` 버킷 | 로컬 적용 성공, RLS 차단 SQL 테스트 | — |
| P2 | `supabase_client.py` + JWT 검증 Depends + plan(free/pro) Depends + 보호 더미 엔드포인트 | 401/200, free/pro 판별 테스트 | P1 |
| P3 | Pydantic 스키마(`metrics.py` 포함) + 리소스 CRUD 헬퍼 | 단위 테스트 | P1 |
| P4 | `openai_client.py`: JSON Schema 구조화 출력 + 재시도 + temperature=0·seed 고정 옵션 | 모킹 단위 테스트 | — (P1과 병렬) |
| P5 | `jobs.py`: 잡 상태 기록 + ProcessPoolExecutor 실행기 추상화 | CPU 더미 잡 실행 중 `/health` 비차단 확인 | P3 |
| P6 | `POST /resumes`·`/job-postings` 텍스트 파싱 | 실제 텍스트 e2e | P2,P3,P4 |
| P7 | PDF 업로드 경로: pypdf 추출 + 국문 PDF 3종 추출 검증 | 추출 품질 확인, 미달 시 pdfplumber 전환 결정 | P6 |
| P8 | `POST /sessions` 적합도+질문 8개 생성, `GET /sessions(/{id})` 폴링 | 카테고리 분포·상태 전이 확인 | P5,P6 |
| P9 | ffmpeg 래퍼: wav 추출 + 프레임 샘플링(fps 결정 포함), 타임아웃 | 샘플 영상 단위 테스트, 손상 파일 처리 | — (P8과 병렬) |
| P10 | `POST /sessions/{id}/answers` multipart + Storage 업로드 + 임시파일 수명주기 + `GET /answers/{id}` | 실패 시 잔존 파일 0 확인 | P5,P9 |
| P11 | VAD 모듈(silero-vad ONNX): 발화/침묵 구간, `silent_seconds`/`pause_count` | 샘플 3종 방향성 테스트 | P9 |
| P12 | STT 모듈: whisper-1 + word timestamps + 필러 프롬프트 + VAD 구간 선처리 | 필러 검출률 측정, 무음 환각 부재 확인 | P11 |
| P13 | `audio_metrics.py` 나머지: wpm, filler, librosa, parselmouth | 빠른/느린/침묵 샘플 방향성 | P11,P12 |
| P14 | 오디오 파이프라인 결합 → `answers.metrics.audio` + transcript 저장 | 업로드→폴링 e2e | P10,P13 |
| P15 | MediaPipe 모델 관리 + 프레임 공급 방식 확정 + 얼굴 검출 지표(visible/center/lost) | 샘플 영상 지표 산출 | P9 (P11~P14와 병렬) |
| P16 | head pose 지표(front_face_ratio, turn/nod) + 임계값 상수 모듈 + 처리속도 측정 | 정면 vs 이탈 영상 변별, 1분 영상 처리시간 기록 | P15 |
| P17 | 영상 파이프라인 결합 → `answers.metrics.video` | e2e | P14,P16 |
| P18 | 답변 피드백: 5축 매핑 기준표 + 프롬프트 + `answers.feedback` + `GET /answers/{id}` 완성 | 반복 호출 편차 ±5, 모킹 테스트 | P17 |
| P19 | 종합 리포트 + Pro 게이팅(`locked`) | free/pro 각각 검증 | P18 |
| P20 | weak-questions + `retry_of` + comparison + `score_delta` | 동일 질문 2회 delta 정합성 | P19 |
| P21 | 운영: retention 삭제 배치 + STT/LLM 재시도 + 구조화 로깅 + 부분 결과 보존 | 실패 주입 테스트, 자동 삭제 확인 | P20 |
| P22 | 부하 측정 + 임계값 튜닝(매핑표·head pose) | 변별력 확인, 큐 전환 판단 기록 | P21 |

**Phase 9 (RAG) 별도 트랙**:
- P9-0: AI Hub 데이터 사용 신청·다운로드 — 승인 리드타임이 있으므로 트랙 착수 시 가장 먼저
- P9-1: pgvector 활성화 + 임베딩·검색 모듈(`rag.py`)
- P9-2: NCS 수집 → 세분류 정규화(`ncs_code`) → 질문 생성 프롬프트 주입
- P9-3: AI Hub 전처리 → 질문 은행 → peer 통계 집계
- 의존: P9-1 → P9-2/P9-3 (병렬 가능), P9-0은 P9-3 이전 아무 때나

**순서 원칙**:
1. 잡 실행기(P5)를 LLM 기능보다 먼저 확립 — 이후 모든 비동기 작업의 토대
2. 오디오 트랙(P11~P14)과 영상 트랙(P15~P16)은 P9 완료 후 병렬 진행 가능

---

## 주요 결정 사항

- **실시간 STT 자막**: 모바일 로컬 기능 — 기기(Expo) STT의 partial transcript를 앱이 직접 화면에 표시하며, 서버는 관여하지 않는다(WebSocket 중계 없음). 분석·저장 기준 transcript는 항상 서버 Whisper(Phase 4) — 기기 STT는 군말("음", "어")을 정규화·제거하고, Android는 word-level 타임스탬프를 사실상 제공하지 않아(API 34+ 일부 기기만) `filler_count`/`speech_rate_wpm` 산출에 사용할 수 없고 플랫폼 간 지표 공정성도 깨진다. 또한 서버 transcript가 있어야 지표 로직 변경 시 과거 답변 재분석이 가능하다(영상은 단기 보관 후 삭제).
  ※ 프론트 확인 사항(서버 범위 외): 영상 녹화(expo-camera)와 기기 STT 동시 동작은 오디오 세션 충돌 가능성이 있어 실기기 검증 필요 — 실패 시 자막 기능 쪽만 조정하면 되고 서버 설계에는 영향 없음.
- **STT 모델·전처리**: whisper-1 고정(word-level 타임스탬프는 whisper-1만 지원, gpt-4o-transcribe 미지원). silero-vad(ONNX, torch 불필요)로 발화 구간을 추출해 그 구간만 Whisper에 투입 — 무음 환각 방지 + 비용 절감(Phase 4).
- **비동기 실행**: MVP는 FastAPI BackgroundTasks를 쓰되, CPU-bound 분석은 `jobs.py`의 ProcessPoolExecutor 실행기로 격리(Phase 2) — GIL로 인한 이벤트 루프 블로킹 방지. 큐(Celery/ARQ) 전환은 Phase 8 부하 측정 후 판단.
- **눈동자 추적**: 정밀 iris 추적 대신 얼굴 방향(head pose) 기반 "정면 응시 추정"으로 설계(Phase 5).
- **Pro 요금제 노출 제어**: 프론트·백엔드 이중 제어. 백엔드는 Supabase로 인증·`profiles.plan` 확인 후 deep_analysis 반환 여부를 결정(Phase 1, 6) — 프론트 잠금은 UX용, 백엔드가 최종 방어선.
- **파인튜닝**: 사용하지 않음 (범위 외 유지).
- **RAG**: MVP(Phase 1~7)에는 미도입 — 현재 LLM 입력(이력서/JD/transcript/metrics)은 전부 컨텍스트에 들어가는 크기라 검색이 불필요. Phase 9에서 외부 공개 데이터(NCS 직무 역량, AI Hub 채용면접 데이터) 기반으로 도입 — 질문 생성 품질·peer 기준값 보강 목적. 인프라는 Supabase pgvector + OpenAI embeddings (별도 벡터 DB 없음). DART 기업 공시 기반 "지원 기업 분석"은 후순위 검토(비상장사 커버리지 한계).
- **AI Hub 데이터 라이선스**: 영리 서비스 활용 허용(약관의 "상업적 이용 별도 협의"는 데이터셋 자체 판매 대상). 단 원문 재제공 금지 — 데이터셋 텍스트의 사용자 노출 금지, few-shot·통계 집계만 사용. NIA 출처 표기 의무.
