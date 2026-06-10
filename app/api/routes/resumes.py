"""이력서 등록·파싱 API (Step 1).

- POST /resumes: 파일 업로드 또는 텍스트 붙여넣기 → LLM 파싱 결과 반환
- GET /resumes/{resume_id}: 파싱된 이력서 프로필 조회

구현은 Phase 2 (docs/plan/implementation-plan.md 참고).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/resumes", tags=["resumes"])
