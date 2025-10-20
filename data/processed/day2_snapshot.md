# Day2 RAG Snapshot — 2025-10-20 21:54
- **Question**: 의료영상 AI 규제의 핵심 포인트는?
- **RAW_DIR**: `data/raw` | **EXTS**: pdf, txt, md

## Retrieval Hits
| # | 제목 | 점수 | 출처 |
|---:|---|---:|---|
| 1 | [Tech Legal Insights.pdf](data/raw/Tech Legal Insights.pdf) | 0.550 | `data/raw/Tech Legal Insights.pdf` |
| 2 | [Tech Legal Insights.pdf](data/raw/Tech Legal Insights.pdf) | 0.520 | `data/raw/Tech Legal Insights.pdf` |
| 3 | [Tech Legal Insights.pdf](data/raw/Tech Legal Insights.pdf) | 0.515 | `data/raw/Tech Legal Insights.pdf` |
| 4 | [KCI_FI002904304(Medical AI regulation).pdf](data/raw/KCI_FI002904304(Medical AI regulation).pdf) | 0.499 | `data/raw/KCI_FI002904304(Medical AI regulation).pdf` |
| 5 | [KCI_FI002904304(Medical AI regulation).pdf](data/raw/KCI_FI002904304(Medical AI regulation).pdf) | 0.493 | `data/raw/KCI_FI002904304(Medical AI regulation).pdf` |

## Web Search
| # | 제목 | 도메인 | 요약 |
|---:|---|---|---|
| 1 | [의료영상 AI 기술의 규제 동향과 PACS 통합 방법](https://goodgyeol.co.kr/28) | `goodgyeol.co.kr` | AI 의료영상 기술에 대한 규제는 크게 세 가지 핵심 원칙을 중심으로 전개됩니다. 첫째, **SaMD(Software as a Medical Device)**는 소프트웨어 단독으로 |
| 2 | [의료 AI 영상 분석: 규제 동향과 PACS 통합 실무](https://goodgyeol.co.kr/19) | `goodgyeol.co.kr` | 이처럼 의료 AI 규제는 기술보다 “신뢰성과 관리 체계”를 중심으로 고도화되고 있으며, 병원은 단순 도입을 넘어 법적 리스크 대응 프로세스까지 함께 |
| 3 | [[PDF] 글로벌 인공지능 병리 ·영상의료기기 산업 ·제도 동향](https://www.khidi.or.kr/kohes/fileDownload?titleId=447137&fileId=1&fileDownType=C&paramMenuId=MENU02462) | `www.khidi.or.kr` | ... 의 상이한 규제와 강화된 법규는 AI 의료영상기기 성장의 주요. 장애물 중 하나로 작용. - 의료영상에 AI 기반 기술을 적용할 경우 각국 규제당국이 정한 AI 의료영상기기 |

## Answer (with citations)
- 위험기반 규제와 허가·심사: 위험등급은 ‘사용목적’에 기초하되, 자율 학습·진화를 고려해 2025년 식약처 ‘인공지능기술이 적용된 디지털의료기기 허가·심사가이드라인’에 따라 적용 알고리즘(기계학습 포함) 관련 자료 제출이 요구됨 [ref2:Tech Legal Insights.pdf|LIN]
- 변경관리: 의료영상 AI를 포함한 디지털 의료기기는 소프트웨어(언어·운영환경, 통신기능 등)와 하드웨어의 사후 변경을 ‘핵심적 성능’ 변경으로 폭넓게 보아 변경허가·심사 대상이 되며, 외관·치수 등 안전·성능에 영향 없는 경미 변경만 예외로 함 [ref1:Tech Legal Insights.pdf|LIN]
- 설명가능성 요구: 생성형 AI의 ‘설명불가능성’이 인정되지만, 규제상은 AI 의료기기의 신뢰성·한계를 설명할 수 있으면 충분하고 내부 판단근거의 해석 가능성까지는 요구되지 않음(Black Box는 기술적 쟁점) [ref3:Tech Legal Insights.pdf|LIN] [ref2:Tech Legal Insights.pdf|LIN]
- 의료진의 설명의무 연계: 의료법상 환자 설명의무는 계속되나, AI 내부 작동의 해석 가능성은 법적 설명의무와 직접 연계되지 않음 [ref3:Tech Legal Insights.pdf|LIN] [ref2:Tech Legal Insights.pdf|LIN]

한계와 다음 액션: 본 컨텍스트는 의료영상 특화 세부기준이 아니라 디지털·생성형 AI 전반 가이드에 기반함. 해당 가이드라인 원문을 검토해 사용목적 정의, 알고리즘 문서화, 변경관리 계획을 의료영상 사용사례에 맞게 구체화할 것을 권고함.