"""영상 지표 산출 — OpenCV + MediaPipe Face Landmarker.

얼굴 감지율, 얼굴 중앙 유지율, 고개 좌우·상하 이탈, 정면 응시 추정 비율,
얼굴 미검출 시간을 계산해 VideoMetrics로 반환.
정밀 눈동자 추적이 아닌 얼굴 방향·위치 기반 "정면 응시 추정"이 MVP 기준.

구현은 Phase 5 (docs/plan/implementation-plan.md 참고).
"""
