# Setup Guide

이 문서는 현재 `pipeline_config.yaml` 기준 **primary choice 구성**에서 필요한 모든 설치 항목을 정리합니다.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                   실행 환경 분류                              │
├─────────────────────────────┬───────────────────────────────┤
│       🖥️  LOCAL (GPU/MPS)    │       🌐 API (무료만)          │
├─────────────────────────────┼───────────────────────────────┤
│ Qwen3.5-27B Q8     (~29GB) │ qwen3.6-plus:free (OpenRouter)│
│ MinerU / magic-pdf (~6GB)  │ Gemini Flash (fallback)       │
│ BGE-M3             (~2GB)  │ Zotero Web API               │
├─────────────────────────────┼───────────────────────────────┤
│ VLM 할당: 최대 32GB        │ 총 비용: $0                   │
│ 총 시스템: 64GB            │                               │
│ (Mac Studio M2 Ultra /     │                               │
│  Mac Mini M4 Pro)          │                               │
└─────────────────────────────┴───────────────────────────────┘
```

---

## 1. 로컬 설치 항목 (Local Models & Tools)

### 1.1 MinerU — PDF 파싱 엔진

| 항목 | 값 |
|---|---|
| 역할 | Stage 1: PDF → 구조화 텍스트 + 그림/표/수식 추출 |
| 패키지 | `magic-pdf[full]` |
| 포함 모델 | DocLayout-YOLO (레이아웃), UniMERNet (수식), PaddleOCR (OCR), StructEqTable (표) |
| GPU VRAM | ~6 GB |
| 디스크 | ~5 GB (모델 가중치 자동 다운로드) |
| 라이선스 | AGPL-3.0 |

```bash
pip install -U "magic-pdf[full]" --extra-index-url https://wheels.myhloli.com
```

### 1.2 Qwen3.5-27B — 비전-언어 모델 (Figure 해석)

| 항목 | 값 |
|---|---|
| 역할 | Stage 1: 그림 초기 설명 / Stage 3: 그림 심층 해석 (축, 범례, 데이터 추정) |
| 모델 | Qwen3.5-27B (네이티브 VLM — 텍스트+이미지 early fusion) |
| 양자화 | Q8_0 (~29GB) — 32GB 할당 내 최고 품질 |
| 서빙 | Ollama 또는 MLX-VLM (Apple Silicon 최적화) |
| 라이선스 | Apache 2.0 |

```bash
# Option A: Ollama (권장 — 간편)
brew install ollama        # macOS
ollama pull qwen3.5:27b    # Q4 기본 (~16GB) 또는
ollama pull qwen3.5:27b-q8_0  # Q8 (~29GB, 최고 품질)
ollama serve               # http://localhost:11434

# Option B: MLX-VLM (Apple Silicon 최적화, ~20-30% 빠름)
pip install mlx-vlm
mlx_vlm.server --model mlx-community/Qwen3.5-27B-8bit --port 8080
```

**참고**: Qwen3.5-27B는 Qwen3-VL 시리즈의 상위 호환. 27B dense 전체 활성으로 MoE 모델(35B-A3B의 활성 3B)보다 figure 해석 품질 우월.

### 1.3 BGE-M3 — 임베딩 모델

| 항목 | 값 |
|---|---|
| 역할 | 구조화 출력 → 다중 레벨 임베딩 (L0~L4) |
| 모델 ID | `BAAI/bge-m3` |
| GPU VRAM | ~2 GB |
| 디스크 | ~2 GB |
| 특성 | dense + sparse + multi-vector 하이브리드 |
| 라이선스 | MIT |

```bash
pip install FlagEmbedding>=1.2.0 sentence-transformers>=3.0.0

# 모델 다운로드
python -c "
from FlagEmbedding import BGEM3FlagModel
BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
"
```

### 1.4 Python 핵심 패키지

```bash
# 데이터 모델 & 설정
pip install pydantic>=2.0 pyyaml>=6.0

# 피드백 웹 UI
pip install fastapi>=0.115.0 uvicorn>=0.30.0

# Zotero 연동
pip install pyzotero>=1.5.0

# CLI 출력
pip install rich>=13.0

# PDF 조작
pip install pymupdf>=1.24.0 Pillow>=10.0

# 데이터베이스 (피드백 저장)
pip install sqlalchemy>=2.0
```

---

## 2. API 호출 항목 (External APIs — 무료만)

### 2.1 OpenRouter — Qwen3.6-Plus:free (추론 LLM)

| 항목 | 값 |
|---|---|
| 역할 | Stage 2: 논증 추출, 가설 형식화 / Stage 3: 예측 생성, 예측-관찰 매칭 / Stage 4: 토론 분석 / Review Agent |
| API Endpoint | `https://openrouter.ai/api/v1/chat/completions` |
| 모델명 | `qwen/qwen3.6-plus:free` |
| 가격 | $0/M input tokens, $0/M output tokens |
| Context | 1,000,000 tokens |
| 특성 | Hybrid architecture (linear attention + sparse MoE), CoT reasoning |
| 프로토콜 | OpenAI-compatible API |

```bash
# API 키 발급: https://openrouter.ai/settings/keys
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# 설치 (OpenAI-compatible client)
pip install openai>=1.50.0

# 테스트
python -c "
from openai import OpenAI
client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key='sk-or-v1-...')
r = client.chat.completions.create(
    model='qwen/qwen3.6-plus:free',
    messages=[{'role':'user','content':'Hello'}]
)
print(r.choices[0].message.content)
"
```

**참고**: 무료 tier는 preview 기간 한정일 수 있음. 프롬프트/완성 데이터가 모델 개선에 사용될 수 있으므로 미공개 논문은 로컬 모델만 사용.

### 2.2 Gemini Flash — 추론 LLM (Fallback)

| 항목 | 값 |
|---|---|
| 역할 | DeepSeek 장애 시 대체용 |
| API Endpoint | Google AI Studio |
| 모델명 | `gemini-2.5-flash` |
| 가격 | 무료 tier (AI Studio: 분당 15 요청, 일 1500 요청) |

```bash
# API 키 발급: https://aistudio.google.com/apikey
export GOOGLE_API_KEY="AIza..."

# 설치
pip install google-genai>=1.0.0
```

### 2.3 Zotero Web API — 논문 소스

| 항목 | 값 |
|---|---|
| 역할 | 사용자 Zotero 라이브러리에서 논문 목록 조회 + PDF 다운로드 |
| API Endpoint | `https://api.zotero.org` |
| 가격 | 무료 |

```bash
# API 키 발급: https://www.zotero.org/settings/keys
# Library ID 확인: https://www.zotero.org/settings/keys → "Your userID for API calls"
export ZOTERO_API_KEY="your-key"
export ZOTERO_LIBRARY_ID="your-user-id"
```

---

## 3. requirements.txt (통합)

```
# ─── Core ───────────────────────────────────────────────────
pydantic>=2.0
pyyaml>=6.0
rich>=13.0

# ─── PDF Parsing (MinerU + dependencies) ────────────────────
magic-pdf[full]
pymupdf>=1.24.0
Pillow>=10.0

# ─── VLM: Qwen3-VL-8B (local GPU) ──────────────────────────
torch>=2.1.0
transformers>=4.45.0
accelerate>=0.30.0
qwen-vl-utils>=0.0.14

# ─── Embedding: BGE-M3 (local GPU) ─────────────────────────
FlagEmbedding>=1.2.0
sentence-transformers>=3.0.0

# ─── API clients (DeepSeek free / Gemini free) ──────────────
openai>=1.50.0
google-genai>=1.0.0

# ─── Zotero integration ────────────────────────────────────
pyzotero>=1.5.0

# ─── Feedback Web UI ───────────────────────────────────────
fastapi>=0.115.0
uvicorn>=0.30.0

# ─── Database ──────────────────────────────────────────────
sqlalchemy>=2.0
```

---

## 4. 환경변수 요약

```bash
# .env 파일 또는 shell profile에 추가

# OpenRouter (무료) — 추론 LLM 전체
export OPENROUTER_API_KEY="sk-or-v1-..."

# Gemini (무료) — 대체 추론 LLM
export GOOGLE_API_KEY="AIza..."

# Zotero — 논문 소스
export ZOTERO_API_KEY="..."
export ZOTERO_LIBRARY_ID="..."
```

---

## 5. 하드웨어 요구사항

### 현재 구성 (Mac Studio M2 Ultra / Mac Mini M4 Pro, 64GB)
- **총 RAM**: 64 GB unified memory
- **VLM 할당**: 32 GB → Qwen3.5-27B Q8 (~29GB)
- **나머지**: MinerU (~6GB) + BGE-M3 (~2GB) — VLM과 순차 실행
- **디스크**: ~35 GB (모델 가중치)

### 최소 사양 (API-only 모드)
- CPU: 8코어, RAM: 16 GB, GPU 불필요
- MinerU CPU 모드 + 모든 추론 OpenRouter API

---

## 6. Quick Start

```bash
# 1. Clone
git clone https://github.com/Joonoh991119/deep-paper-reader.git
cd deep-paper-reader

# 2. 가상환경
conda create -n dpr python=3.10
conda activate dpr

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경변수
cp .env.example .env
# .env 편집하여 OPENROUTER_API_KEY 등 입력

# 5. Ollama로 VLM 설치 + 실행
brew install ollama
ollama pull qwen3.5:27b-q8_0    # ~29GB 다운로드
ollama serve                      # 백그라운드 실행

# 6. Zotero에서 논문 목록 확인
python -c "from src.zotero_client import zotero_list_command; zotero_list_command()"

# 7. 논문 처리
python -m src.pipeline /path/to/paper.pdf -o ./output

# 8. 피드백 웹 UI 실행
uvicorn src.feedback_loop.web_ui:app --port 8501
# → http://localhost:8501
```

---

## 7. 모델별 역할 매핑 (한눈에)

```
Pipeline Stage          Model                    Where       Cost
──────────────────────────────────────────────────────────────────
Stage 1: PDF 파싱       MinerU                   🖥️ Local     Free
Stage 1: 레이아웃       DocLayout-YOLO           🖥️ Local     Free (MinerU 내장)
Stage 1: OCR            PaddleOCR                🖥️ Local     Free (MinerU 내장)
Stage 1: 수식 인식      UniMERNet                🖥️ Local     Free (MinerU 내장)
Stage 1: 표 인식        StructEqTable            🖥️ Local     Free (MinerU 내장)
Stage 1: 그림 설명      Qwen3.5-27B Q8 (Ollama)  🖥️ Local     Free
──────────────────────────────────────────────────────────────────
Stage 2: 논증 추출      qwen3.6-plus:free        🌐 OpenRouter  $0
Stage 2: 가설 형식화    qwen3.6-plus:free        🌐 OpenRouter  $0
──────────────────────────────────────────────────────────────────
Stage 3: 그림 심층해석  Qwen3.5-27B Q8 (Ollama)  🖥️ Local     Free
Stage 3: 예측 생성      qwen3.6-plus:free        🌐 OpenRouter  $0
Stage 3: 예측 매칭      qwen3.6-plus:free        🌐 OpenRouter  $0
──────────────────────────────────────────────────────────────────
Stage 4: 토론 분석      qwen3.6-plus:free        🌐 OpenRouter  $0
──────────────────────────────────────────────────────────────────
Review Agent            qwen3.6-plus:free        🌐 OpenRouter  $0
Embedding               BGE-M3                   🖥️ Local     Free
Paper Source            Zotero API               🌐 Zotero     Free
──────────────────────────────────────────────────────────────────
Fallback LLM            Gemini 2.5 Flash         🌐 Google     Free tier
```
