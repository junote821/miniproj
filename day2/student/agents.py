from typing import List, Dict

def answer_with_context(question: str, contexts: List[Dict], k_refs: int = 3) -> str:
    """
    TODO-D2-11: 상위 컨텍스트를 묶어 간단 답변(마크다운) 생성
    - 형태:
      ### Answer (from local KB)
      <요약/답변>

      [ref1:제목|출처]
      [ref2:제목|출처]
    - 컨텍스트 없으면 안내 메시지
    """
    if not contexts:
        return "_관련 문서를 찾지 못했습니다._"
    refs = []
    for i, c in enumerate(contexts[:k_refs], 1):
        title = c.get("title","doc")
        src = c.get("source","")
        refs.append(f"[ref{i}:{title}|{src}]")
    body = "질의에 대한 핵심 근거를 상위 문서에서 발췌했습니다. 세부 내용은 각 ref를 확인하세요."
    return "### Answer (from local KB)\n\n" + body + "\n\n" + "\n".join(refs)
