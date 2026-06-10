"""면접 세션 API (Step 3 AI 분석, Step 6 재도전, 허브 목록).

- POST /sessions: 세션 생성 + 적합도 매칭/질문 생성 잡 시작 (202)
- GET /sessions: 지난 세션 목록 (허브 화면)
- GET /sessions/{session_id}: 상태 폴링 + 적합도/질문 조회
- GET /sessions/{session_id}/weak-questions: 약점 질문 목록 (재도전)

구현은 Phase 2·7 (docs/plan/implementation-plan.md 참고).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/sessions", tags=["sessions"])
