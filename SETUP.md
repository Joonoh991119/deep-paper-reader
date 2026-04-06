# Setup Guide

이 문서는 현재 `pipeline_config.yaml` 기준 **primary choice 구성**에서 필요한 모든 설치 항목을 정리합니다.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                   실행 환경 분류                              │
├─────────────────────────────┬───────────────────────────────┤
│       🖥️  LOCAL (GPU)        │       🌐 API (무료만)          │
├─────────────────────────────┼───────────────────────────────┤
│ Qwen3-VL-8B       (16GB)   │ DeepSeek-R1  (무료 tier)      │
│ MinerU / magic-pdf (~6GB)  │ Gemini Flash (무료 tier, 대체) │
│ BGE-M3             (~2GB)  │ Zotero Web API (무료)         │
│ PaddleOCR          (~1GB)  │                               │
│ DocLayout-YOLO     (~1GB)  │                               │
├─────────────────────────────┼───────────────────────────────┤
│ 총 GPU VRAM: ~20GB         │ 총 비용: $0                   │
│ 총 디스크:   ~15GB         │                               │
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

### 1.2 Qwen3-VL-8B — 비전-언어 모델 (Figure 해석)

| 항목 | 값 |
|---|---|
| 역할 | Stage 1: 그림 초기 설명 / Stage 3: 그림 심층 해석 (축, 범례, 데이터 추정) |
| 모델 ID | `Qwen/Qwen3-VL-8B-Instruct` |
| GPU VRAM | ~16 GB (bf16) |
| 디스크 | ~16 GB |
| 라이선스 | Apache 2.0 |

```bash
pip install transformers>=4.45.0 torch>=2.1.0 accelerate>=0.30.0
pip install qwen-vl-utils>=0.0.14

# 모델 다운로드 (첫 실행 시 자동, 또는 수동)
python -c "
from transformers import AutoProcessor, AutoModelForCausalLM
AutoProcessor.from_pretrained('Qwen/Qwen3-VL-8B-Instruct')
AutoModelForCausalLM.from_pretrained('Qwen/Qwen3-VL-8B-Instruct')
"
```

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

### 2.1 DeepSeek-R1 — 추론 LLM (Primary)

| 항목 | 값 |
|---|---|
| 역할 | Stage 2: 논증 추출, 가설 형식화 / Stage 3: 예측 생성, 예측-관찰 매칭 / Stage 4: 토론 분석 / Review Agent |
| API Endpoint | `https://api.deepseek.com/v1/chat/completions` |
| 모델명 | `deepseek-reasoner` (R1) 또는 `deepseek-chat` (V3) |
| 가격 | 무료 tier 제공 (가입 시 크레딧) |
| 프로토콜 | OpenAI-compatible API |

```bash
# API 키 발급: https://platform.deepseek.com/api_keys
export DEEPSEEK_API_KEY="sk-your-key-here"

# 설치
pip install openai>=1.50.0  # OpenAI-compatible client 사용
```

**참고**: DeepSeek-R1을 로컬에서 돌릴 수도 있음 (70B+ 모델, multi-GPU 필요).
로컬 배포 시 vLLM 또는 SGLang 사용:
```bash
# 로컬 배포 (선택사항 — GPU 여유 시)
pip install vllm
vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-32B --port 8000
# pipeline_config.yaml에서 base_url을 http://localhost:8000/v1 로 변경
```

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

# DeepSeek (무료) — 추론 LLM
export DEEPSEEK_API_KEY="sk-..."

# Gemini (무료) — 대체 추론 LLM
export GOOGLE_API_KEY="AIza..."

# Zotero — 논문 소스
export ZOTERO_API_KEY="..."
export ZOTERO_LIBRARY_ID="..."
```

---

## 5. 하드웨어 요구사항

### 최소 사양 (API 모드)
- CPU: 8코어
- RAM: 16 GB
- GPU: 없어도 가능 (MinerU CPU 모드 + 모든 추론 API)
- 디스크: 10 GB

### 권장 사양 (로컬 모델 전체)
- CPU: 8+ 코어
- RAM: 32 GB
- **GPU: NVIDIA 24GB VRAM** (RTX 4090 / A5000 / etc.)
  - Qwen3-VL-8B: ~16 GB
  - MinerU: ~6 GB
  - BGE-M3: ~2 GB
  - (동시 실행하지 않으므로 24GB면 충분)
- 디스크: 30 GB (모델 가중치 포함)

### Mac Studio (M2 Max Ultra) 사용 시
- `gpu_device: "mps"` 로 변경
- Qwen3-VL-8B: MPS 호환 (unified memory 활용)
- MinerU: CPU 모드 또는 MPS

### GPU 서버 확장 시
- Qwen3-VL-72B: 80GB+ VRAM (2× A100 또는 H100)
- DeepSeek-R1 로컬: 70B+ 모델, multi-GPU + vLLM

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
# .env 편집하여 API 키 입력

# 5. Zotero에서 논문 목록 확인
python -c "from src.zotero_client import zotero_list_command; zotero_list_command()"

# 6. 논문 처리
python -m src.pipeline /path/to/paper.pdf -o ./output

# 7. 피드백 웹 UI 실행
uvicorn src.feedback_loop.web_ui:app --port 8501
# → http://localhost:8501 에서 접속
```

---

## 7. 모델별 역할 매핑 (한눈에)

```
Pipeline Stage          Model              Where      Cost
─────────────────────────────────────────────────────────────
Stage 1: PDF 파싱       MinerU             🖥️ Local    Free
Stage 1: 레이아웃       DocLayout-YOLO     🖥️ Local    Free  (MinerU 내장)
Stage 1: OCR            PaddleOCR          🖥️ Local    Free  (MinerU 내장)
Stage 1: 수식 인식      UniMERNet          🖥️ Local    Free  (MinerU 내장)
Stage 1: 표 인식        StructEqTable      🖥️ Local    Free  (MinerU 내장)
Stage 1: 그림 설명      Qwen3-VL-8B        🖥️ Local    Free
─────────────────────────────────────────────────────────────
Stage 2: 논증 추출      DeepSeek-R1        🌐 API     Free tier
Stage 2: 가설 형식화    DeepSeek-R1        🌐 API     Free tier
─────────────────────────────────────────────────────────────
Stage 3: 그림 해석      Qwen3-VL-8B        🖥️ Local    Free
Stage 3: 예측 생성      DeepSeek-R1        🌐 API     Free tier
Stage 3: 예측 매칭      DeepSeek-R1        🌐 API     Free tier
─────────────────────────────────────────────────────────────
Stage 4: 토론 분석      DeepSeek-R1        🌐 API     Free tier
─────────────────────────────────────────────────────────────
Review Agent            DeepSeek-R1        🌐 API     Free tier
Embedding               BGE-M3             🖥️ Local    Free
Paper Source            Zotero API         🌐 API     Free
─────────────────────────────────────────────────────────────
Fallback LLM            Gemini 2.5 Flash   🌐 API     Free tier
```
