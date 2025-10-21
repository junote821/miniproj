import os, numpy as np
from typing import List, Dict
from litellm import embedding

EMB_MODEL = os.getenv("EMBEDDING_MODEL","text-embedding-3-small")

def _embed(texts: List[str]) -> np.ndarray:
    """
    TODO-8: 임베딩 호출
      - litellm.embedding(model=EMB_MODEL, input=text)
      - L2 정규화 후 반환
      - 예외 처리 포함
    """
    raise NotImplementedError("TODO-8: 임베딩 호출 및 정규화를 구현하세요.")

def rank_items(query: str, items: List[Dict], w_sim=0.6, w_recency=0.4)->List[Dict]:
    """
    TODO-9: (query, items) → total score
      - sim: cosine(Q, title+summary)
      - recency: date 있으면 +1.0, 없으면 0.0
      - total = w_sim*sim + w_recency*recency, 내림차순 정렬
    """
    raise NotImplementedError("TODO-9: rank_items를 구현하세요.")
