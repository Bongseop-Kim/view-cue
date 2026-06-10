"""view-cue FastAPI 앱 엔트리포인트."""

from fastapi import FastAPI

from app.api.routes import answers, health, job_postings, reports, resumes, sessions

app = FastAPI(
    title="view-cue API",
    description="면접 영상 분석 및 LLM 피드백 리포트 생성 서버",
    version="0.1.0",
)

API_PREFIX = "/api/v1"

app.include_router(health.router)
app.include_router(resumes.router, prefix=API_PREFIX)
app.include_router(job_postings.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)
app.include_router(answers.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
