# Test Corpus — Pipeline Validation Papers

Zotero 라이브러리에서 선정한 10편. 다양한 논문 유형을 커버하도록 구성.

## Selection Criteria
- PDF 첨부파일 있는 논문만 선정
- 컬렉션 다양성: Efficient Coding, Perceptual Bias, BDM, fMRI
- 유형 다양성: 이론, 행동실험, 계산모델링, 리뷰
- Figure 유형 다양성: 라인 플롯, 바 차트, 히트맵, 뇌 이미지, 모델 도식

---

## Papers

### 1. Park & Pillow (2024) — Bayesian Efficient Coding
- **Zotero key**: `8IZV4BEV`
- **Collection**: Efficient Coding
- **Type**: Computational/theoretical
- **Why selected**: 핵심 이론 논문. 수식 heavy, 모델 도식 + 시뮬레이션 결과 그림
- **DOI**: 10.1101/178418

### 2. Wei & Stocker (2016) — Mutual Information, Fisher Information, and Efficient Coding
- **Zotero key**: `EDCYGU7P`
- **Collection**: Efficient Coding
- **Type**: Computational/theoretical
- **Why selected**: Fisher info vs mutual info 수리적 관계. 수식 + 도식 그림 풍부
- **DOI**: 10.1162/NECO_a_00804

### 3. Prat-Carrabin & Woodford (2020) — Efficient coding of numbers explains decision bias and noise
- **Zotero key**: `A5UUMF7X`
- **Collection**: Efficient Coding
- **Type**: Empirical + computational
- **Why selected**: 행동 데이터 + 모델 피팅. 바 차트, 산점도, 모델 비교 그림
- **DOI**: 10.1101/2020.02.18.942938

### 4. Ceylan & Pascucci (2023) — Attractive and repulsive serial dependence
- **Zotero key**: `K3LACFBF`
- **Collection**: Perceptual Bias
- **Type**: Empirical (psychophysics)
- **Why selected**: 전형적인 행동실험 논문. 조건별 라인 플롯, 개인차 산점도
- **DOI**: 10.1167/jov.23.6.8

### 5. Bliss, Sun & D'Esposito (2017) — Serial dependence absent at perception, increases in VWM
- **Zotero key**: `N7A3I5IE`
- **Collection**: Perceptual Bias
- **Type**: Empirical (psychophysics + modeling)
- **Why selected**: 시간 경과에 따른 serial dependence 변화. 복잡한 multi-panel 그림
- **DOI**: 10.1038/s41598-017-15199-7

### 6. Cicchini, Mikellidou & Burr (2018) — The functional role of serial dependence
- **Zotero key**: `N8Q9UDEJ`
- **Collection**: Perceptual Bias
- **Type**: Empirical + computational
- **Why selected**: Kalman filter 모델 + 행동 데이터. 모델-데이터 오버레이 그림
- **DOI**: 10.1098/rspb.2018.1722

### 7. Li, Wang & Zaidel (2026) — Reversed effects of prior choices in cross-modal temporal decisions
- **Zotero key**: `FW8C8TDJ`
- **Collection**: Perceptual Bias
- **Type**: Empirical (psychophysics)
- **Why selected**: 최신 논문 (2026). Attractive vs repulsive 효과 분리. 복잡한 factorial design
- **DOI**: 10.1016/j.cognition.2025.106294

### 8. Hahn, Wang & Wei (2025) — Identifiability of Bayesian Models of Cognition
- **Zotero key**: `VTLG5IJC`
- **Collection**: BDM
- **Type**: Computational/methodological
- **Why selected**: Bayesian model identifiability. 수식 + 시뮬레이션 + 실제 데이터 적용
- **DOI**: 10.1101/2025.06.25.661321

### 9. Sanborn (2017) — Types of approximation for probabilistic cognition
- **Zotero key**: `V6RNQJFF`
- **Collection**: BDM
- **Type**: Review/perspective
- **Why selected**: 리뷰 논문 테스트. 도식 위주, 가설-실험 구조 없음 → 파이프라인 edge case
- **DOI**: 10.1016/j.bandc.2015.06.008

### 10. Acerbi & Ma (2017) — Practical Bayesian Optimization for Model Fitting (BADS)
- **Zotero key**: `DIQBSGUB`
- **Collection**: BDM > Methodology
- **Type**: Methods paper
- **Why selected**: 방법론 논문. 벤치마크 테이블 + 최적화 수렴 그림 + 알고리즘 도식
- **DOI**: 10.48550/arXiv.1705.04405

---

## Coverage Matrix

| Dimension | Papers |
|---|---|
| **Empirical (psychophysics)** | #4, #5, #7 |
| **Computational/theoretical** | #1, #2, #8 |
| **Empirical + computational** | #3, #6 |
| **Methods** | #10 |
| **Review** | #9 |
| **Figure types**: line plots | #4, #5, #6, #7 |
| **Figure types**: scatter/model fit | #3, #6, #8 |
| **Figure types**: model diagrams | #1, #2, #9 |
| **Figure types**: benchmark tables | #10 |
| **Math-heavy** | #1, #2, #8 |
| **Multi-panel complex** | #5, #7 |

---

## Usage

```bash
# Zotero에서 이 10편의 PDF 다운로드
python -c "
from src.zotero_client import ZoteroClient
client = ZoteroClient()

test_keys = [
    '8IZV4BEV', 'EDCYGU7P', 'A5UUMF7X', 'K3LACFBF', 'N7A3I5IE',
    'N8Q9UDEJ', 'FW8C8TDJ', 'VTLG5IJC', 'V6RNQJFF', 'DIQBSGUB',
]

papers = client.list_papers(limit=100)
test_papers = [p for p in papers if p.key in test_keys]
client.download_all_pdfs(test_papers)
"

# 전체 파이프라인 실행 (1편씩)
for pdf in zotero_pdfs/*.pdf; do
    python -m src.pipeline "$pdf" -o "./output/$(basename $pdf .pdf)"
done
```
