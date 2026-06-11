# view-cue API 명세서

프론트엔드 프로토타입(`ai-aptitude-games/docs/prototype/interview-track`)의 6단계 화면 플로우를 기준으로 작성한 REST API 명세.

- Base URL: `/api/v1`
- 인증: Supabase Auth JWT — `Authorization: Bearer <access_token>` (모든 엔드포인트, 검증 구현은 Phase 1)
- 비동기 작업(분석·생성)은 **202 Accepted + 상태 폴링** 패턴을 따른다
- 오류 응답: `{ "error": { "code": string, "message": string } }`

## 화면 ↔ API 매핑

| 화면 (프로토타입) | 단계 | 사용 API |
|------------------|------|---------|
| InterviewHub | 허브 | `GET /sessions` |
| IVResume | Step 1 | `POST /resumes`, `GET /resumes/{id}` |
| IVJob | Step 2 | `POST /job-postings`, `GET /job-postings/{id}` |
| IVAnalysis | Step 3 | `POST /sessions`, `GET /sessions/{id}` (폴링) |
| IVInterview | Step 4 | `POST /sessions/{id}/answers`, `GET /answers/{id}` (폴링) |
| IVFeedback | Step 5 | `POST /sessions/{id}/report`, `GET /sessions/{id}/report` |
| IVRetry | Step 6 | `GET /sessions/{id}/weak-questions`, `POST /sessions/{id}/answers` (retry_of), `GET /answers/{id}/comparison` |

---

## Step 1. 이력서

### POST /resumes

이력서 등록. 파일 업로드(`multipart/form-data`) 또는 텍스트 붙여넣기(`application/json`) 중 하나.

- multipart: `file` (PDF/이미지, 최대 10MB)
- JSON: `{ "text": "이력서 본문..." }`

응답 `201 Created` — 파싱은 동기 처리(LLM 텍스트 파싱, 수 초 내):

```json
{
  "id": "uuid",
  "source_type": "file | text",
  "file_name": "김준비_이력서_2026.pdf",
  "parsed": {
    "name": "김준비",
    "role": "프론트엔드 엔지니어",
    "years": "경력 3년",
    "skills": ["React", "TypeScript", "Next.js"],
    "highlights": ["커머스 웹 프론트엔드 리드 (MAU 80만)", "사내 디자인 시스템 0→1 구축"]
  },
  "created_at": "2026-06-10T09:00:00Z"
}
```

### GET /resumes/{resume_id}

위 응답과 동일한 단건 조회.

---

## Step 2. 채용공고

### POST /job-postings

채용공고 등록. 파일 업로드 또는 텍스트/URL 붙여넣기.

- multipart: `file`
- JSON: `{ "text": "공고 본문 또는 URL" }`

응답 `201 Created`:

```json
{
  "id": "uuid",
  "source_type": "file | text",
  "parsed": {
    "company": "리플로우",
    "role": "프론트엔드 엔지니어 (Senior)",
    "type": "정규직 · 서울 성수",
    "source": "reflow.team/careers/fe-senior",
    "must": ["React · TypeScript 3년+", "디자인 시스템 설계/운영"],
    "nice": ["Next.js App Router", "오픈소스 기여"]
  },
  "created_at": "2026-06-10T09:01:00Z"
}
```

### GET /job-postings/{job_posting_id}

단건 조회.

---

## Step 3. 세션 생성 + AI 분석 (적합도·질문 생성)

### POST /sessions

```json
{ "resume_id": "uuid", "job_posting_id": "uuid" }
```

응답 `202 Accepted` — 백그라운드에서 적합도 매칭 + 질문 8개 생성 시작:

```json
{ "id": "uuid", "status": "analyzing" }
```

### GET /sessions/{session_id}

상태 폴링. `status`: `analyzing` → `ready` → (면접 진행) `in_progress` → `completed` | `failed`

`ready` 이후 응답:

```json
{
  "id": "uuid",
  "status": "ready",
  "resume_id": "uuid",
  "job_posting_id": "uuid",
  "match": {
    "score": 78,
    "matched": [
      { "k": "React · TypeScript", "note": "3년 실무 — 요건 충족", "hit": true },
      { "k": "Next.js App Router", "note": "경험 명시 없음 — 보완 권장", "hit": false }
    ]
  },
  "questions": [
    {
      "id": "uuid",
      "order": 1,
      "cat": "오프닝",
      "text": "1분 안에 자기소개를 부탁드려요.",
      "limit_seconds": 60,
      "why": "면접 도입 — 첫인상과 전달력 확인"
    }
  ],
  "created_at": "2026-06-10T09:02:00Z"
}
```

- `cat` ∈ `오프닝 | 지원 동기 | 경험 | 관계 | 직무 | 인성 | 가치`
- 질문 수 기본 8개

### GET /sessions (허브 목록)

쿼리: `?limit=20&offset=0`

```json
{
  "items": [
    {
      "id": "uuid",
      "company": "리플로우",
      "role": "프론트엔드 엔지니어 (Senior)",
      "status": "completed",
      "overall_score": 74,
      "score_delta": 8,
      "question_count": 8,
      "answered_count": 8,
      "created_at": "2026-01-12T09:00:00Z"
    }
  ],
  "total": 2
}
```

- `score_delta`: 직전 세션 대비 종합 점수 변화 (첫 세션은 `null`)

---

## Step 4. 답변 영상 업로드·분석

### POST /sessions/{session_id}/answers

`multipart/form-data`:

| 필드 | 타입 | 설명 |
|------|------|------|
| `question_id` | uuid | 답변한 질문 |
| `video` | file | 영상 (mp4/mov, 권장 ≤ 200MB, 길이 상한 약 13분 — Whisper API 25MB 제한 기준 서버 검증) |
| `retry_of` | uuid? | 재도전 시 이전 answer id (Step 6) |

응답 `202 Accepted` — 분석 파이프라인(ffmpeg → STT/지표 → LLM 피드백) 시작:

```json
{ "id": "uuid", "status": "processing" }
```

같은 질문에 재업로드("다시 답하기")하면 새 answer가 생성되고 최신 답변이 유효본이 된다.

### GET /answers/{answer_id}

상태 폴링. `status`: `processing` → `done` | `failed`

`done` 응답:

```json
{
  "id": "uuid",
  "session_id": "uuid",
  "question_id": "uuid",
  "status": "done",
  "retry_of": null,
  "duration_seconds": 52.4,
  "transcript": "안녕하세요. 3년 차 프론트엔드 엔지니어 김준비입니다...",
  "metrics": {
    "duration_seconds": 52.4,
    "audio": {
      "speech_rate_wpm": 142.5,
      "silent_seconds": 6.2,
      "pause_count": 4,
      "filler_count": 3,
      "pitch_variation": 28.4,
      "energy_mean": 0.061,
      "volume_variation": 0.18,
      "intonation_monotony": 0.42
    },
    "video": {
      "face_visible_ratio": 0.97,
      "face_center_ratio": 0.88,
      "front_face_ratio": 0.74,
      "head_turn_count": 5,
      "head_nod_count": 2,
      "face_lost_seconds": 1.4
    }
  },
  "feedback": {
    "scores": { "content": 78, "star": 60, "voice": 86, "gaze": 74, "delivery": 82 },
    "good": "말 속도가 안정적이고, 핵심 경력을 앞에 배치해 첫인상이 또렷했어요.",
    "fix": "강점을 지원 직무 요건과 한 문장으로 연결하면 설득력이 올라가요.",
    "improved_answer": "안녕하세요. 디자인 시스템을 0→1로 구축한 3년 차 ...",
    "follow_up_questions": ["디자인 시스템 채택률은 어떻게 측정했나요?"]
  },
  "created_at": "2026-06-10T09:10:00Z"
}
```

- 5축 `scores`: `content`(내용 충실도·관련성), `star`(STAR 구조), `voice`(음성), `gaze`(시선 — 정면 응시 추정), `delivery`(전달력). 0~100.
- `filler_count`는 근사치 — STT(Whisper)가 필러를 정규화·누락하는 경향이 있어 프롬프트로 보존을 유도하지만 보장되지 않는다 (Phase 4 검증에서 검출률 확인).
- `failed` 시: `{ "status": "failed", "error": { "code": "STT_FAILED", "message": "..." } }`

### GET /answers/{answer_id}/comparison (Step 6 비교)

재도전 답변(`retry_of`가 있는 answer)에 대해 이전/이번 비교:

```json
{
  "question": { "id": "uuid", "cat": "관계", "text": "팀 내 의견 충돌을..." },
  "previous": { "answer_id": "uuid", "scores": { "content": 70, "star": 58 }, "transcript": "...", "duration_seconds": 82 },
  "current":  { "answer_id": "uuid", "scores": { "content": 82, "star": 74 }, "transcript": "...", "duration_seconds": 98 },
  "delta": { "content": 12, "star": 16, "voice": 4, "gaze": 6, "delivery": 8 },
  "summary": "결과(Result)를 수치로 마무리하니 STAR +16점. 같은 패턴을 다른 답변에도 적용해 보세요."
}
```

---

## Step 5. 종합 리포트

### POST /sessions/{session_id}/report

전제: 세션의 답변 분석이 모두 `done`. 응답 `202 Accepted`:

```json
{ "session_id": "uuid", "status": "generating" }
```

### GET /sessions/{session_id}/report

`status`: `generating` → `ready` | `failed`

```json
{
  "session_id": "uuid",
  "status": "ready",
  "overall_score": 74,
  "axis_avg": { "content": 76, "star": 62, "voice": 79, "gaze": 67, "delivery": 72 },
  "peer_avg": { "content": 70, "star": 63, "voice": 76, "gaze": 67, "delivery": 71 },
  "peer_percentile": 31,
  "top_fixes": [
    {
      "axis": "star",
      "title": "결과(Result)로 마무리하기",
      "body": "답변 4개에서 결과가 빠졌어요. \"그래서 무엇이 좋아졌는지\"를 수치로 닫아주세요."
    }
  ],
  "deep_analysis": {
    "gaze": { "camera_ratio": 0.68, "down_ratio": 0.22, "etc_ratio": 0.10 },
    "delivery": { "expression_stability": 78, "posture_consistency": 71, "gesture": 64, "speech_pace": 82 }
  },
  "answers": [
    { "answer_id": "uuid", "question_id": "uuid", "order": 1, "cat": "오프닝",
      "scores": { "content": 78, "star": 60, "voice": 86, "gaze": 74, "delivery": 82 } }
  ],
  "created_at": "2026-06-10T09:30:00Z"
}
```

- `peer_avg`/`peer_percentile`: MVP에서는 고정 기준값 테이블 사용, 추후 실데이터 기반 갱신 (Phase 8)
- `deep_analysis`: **Pro 전용** — 백엔드가 `profiles.plan`을 확인해 free 사용자에게는 본문을 제외하고 잠금 표시만 반환한다(Phase 6). 프론트 잠금 UI는 UX용이고 백엔드가 최종 방어선.

  free 사용자 응답:

  ```json
  "deep_analysis": { "locked": true }
  ```

---

## Step 6. 재도전

### GET /sessions/{session_id}/weak-questions

약점 질문 선정 — `content + star` 합산 점수 하위 N개 (기본 3개, `?limit=3`):

```json
{
  "items": [
    {
      "question": { "id": "uuid", "cat": "관계", "text": "팀 내 의견 충돌을 해결한 경험이 있나요?" },
      "answer_id": "uuid",
      "scores": { "content": 70, "star": 58 }
    }
  ]
}
```

재답변은 `POST /sessions/{id}/answers`에 `retry_of`를 넣어 업로드하고,
비교는 `GET /answers/{id}/comparison`으로 조회한다.

---

## 공통

### GET /health (인증 불필요, prefix 없음)

```json
{ "status": "ok" }
```

### 상태 코드 규약

| 코드 | 용도 |
|------|------|
| 200 / 201 | 조회 / 생성 완료 |
| 202 | 비동기 작업 접수 (분석·생성 시작) |
| 400 | 잘못된 입력 (파일 형식/크기 등) |
| 401 | 인증 실패 |
| 404 | 리소스 없음 |
| 409 | 상태 충돌 (예: 분석 미완료 세션에 리포트 요청) |
| 422 | 유효성 검증 실패 |
| 500 | 서버 오류 (분석 실패는 잡 status=failed로 노출) |
