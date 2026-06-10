"""답변 영상 업로드·분석 API (Step 4).

- POST /sessions/{session_id}/answers: 질문별 영상 업로드 → 분석 잡 시작 (202)
- GET /answers/{answer_id}: 상태 폴링 + transcript/metrics/점수/코멘트 조회
- GET /answers/{answer_id}/comparison: 재도전 답변의 이전/이번 비교 (Step 6)

구현은 Phase 3~6 (docs/plan/implementation-plan.md 참고).
"""

from fastapi import APIRouter

router = APIRouter(tags=["answers"])
