"""LLM 피드백·리포트 생성 — OpenAI GPT.

영상 자체는 입력하지 않는다. 질문 + STT transcript + 이력서/JD 요약 +
metrics JSON을 입력으로 5축 점수, 피드백 문장(good/fix), 개선 답변,
꼬리질문, 종합 리포트를 구조화 출력(JSON)으로 생성.

구현은 Phase 2(파싱·질문 생성)·Phase 6(피드백) 참고.
"""
