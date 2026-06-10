"""세션 종합 리포트 API (Step 5 피드백).

- POST /sessions/{session_id}/report: 종합 리포트 생성 잡 시작 (202)
- GET /sessions/{session_id}/report: 종합 점수/5축 평균/개선점/심층 분석 조회

구현은 Phase 6 (docs/plan/implementation-plan.md 참고).
"""

from fastapi import APIRouter

router = APIRouter(tags=["reports"])
