"""채용공고 등록·파싱 API (Step 2).

- POST /job-postings: 파일/텍스트/URL → LLM 파싱 결과 반환
- GET /job-postings/{job_posting_id}: 파싱된 채용공고 조회

구현은 Phase 2 (docs/plan/implementation-plan.md 참고).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/job-postings", tags=["job-postings"])
