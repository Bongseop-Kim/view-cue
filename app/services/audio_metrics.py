"""오디오 지표 산출 — VAD·librosa·parselmouth.

말 빠르기(WPM), 침묵 시간, 멈춤 횟수, 필러 단어 수, 피치 변화,
발화 에너지, 음량 변화, 억양 단조로움을 계산해 AudioMetrics로 반환.

구현은 Phase 4 (docs/plan/implementation-plan.md 참고).
"""
