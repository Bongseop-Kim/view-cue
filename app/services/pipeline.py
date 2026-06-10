"""답변 분석 파이프라인 오케스트레이션.

영상 수신 → ffmpeg로 오디오/프레임 분리 → STT + 오디오 지표 + 영상 지표
→ metrics JSON 저장 → LLM 피드백 생성 → 임시 파일 정리.
각 단계의 상태를 answers.status로 기록해 폴링 API가 노출한다.

구현은 Phase 3~6 (docs/plan/implementation-plan.md 참고).
"""
