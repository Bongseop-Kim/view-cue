"""백그라운드 분석 잡 실행·상태 추상화.

MVP는 FastAPI BackgroundTasks로 실행하되, 잡 상태(pending/processing/done/failed)를
DB에 기록해 폴링 API가 노출한다. 이 모듈 뒤로 실행 방식을 숨겨
추후 Celery/ARQ 등 외부 큐로 교체할 때 호출부 변경을 최소화한다.

구현은 Phase 2 (docs/plan/implementation-plan.md 참고).
"""
