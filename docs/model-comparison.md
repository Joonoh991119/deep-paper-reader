# Model Comparison & Selection Guide

Detailed benchmarks and selection rationale for each pipeline component.

---

## 1. PDF Parsing & Layout Detection

### Decision Matrix

| Model | Type | Scientific Papers | Math Support | Figure Extraction | License | GPU Required | Maturity |
|---|---|---|---|---|---|---|---|
| **MinerU 2.5** | Pipeline | ⭐⭐⭐⭐⭐ (86.2 OmniDocBench) | ✅ UniMERNet | ✅ Built-in | AGPL-3.0 | ~6GB | Production |
| Nougat (Meta) | End-to-end | ⭐⭐⭐⭐ (best for LaTeX) | ✅ Native LaTeX | ❌ Manual | CC-BY-NC | ~8GB | Stable |
| Marker | Pipeline | ⭐⭐⭐ | Partial | Partial | GPL-3.0 | ~4GB | Active |
| Docling (IBM) | Pipeline | ⭐⭐⭐⭐ | ✅ | ✅ | MIT | ~4GB | Active |
| LlamaParse | Cloud API | ⭐⭐⭐ | Partial | ✅ | Commercial | None (API) | Production |
| GPTPDF | Minimal | ⭐⭐⭐ | Via VLM | Via VLM | MIT | None (API) | Experimental |
| PaddleOCR-VL | End-to-end | ⭐⭐⭐⭐ | ✅ | ✅ | Apache 2.0 | ~2GB | New (2025) |

### Recommendation

**Primary: MinerU** — Highest benchmark scores on scientific documents. Built-in figure/table/formula extraction. Born from InternLM pretraining, specifically designed for academic papers.

**Fallback: Nougat** — For papers with heavy mathematical notation where LaTeX preservation matters most. Nougat outputs native LaTeX, which is superior for equation-heavy neuroscience computational papers.

**Watch: PaddleOCR-VL** — New 0.9B model achieves SOTA with minimal resources. Good candidate for edge deployment.

---

## 2. Vision-Language Models (Figure Interpretation)

### Chart/Figure Understanding Benchmarks

| Model | ChartQA | DocVQA | MMMU | MathVista | Size | Self-Host | License | Cost (API) |
|---|---|---|---|---|---|---|---|---|
| **Qwen3-VL-72B** | ~86 | ~95 | ~72 | ~77 | 72B | ✅ (80GB+) | Apache 2.0 | ~$0.15/1M |
| Qwen3-VL-8B | ~78 | ~90 | ~65 | ~70 | 8B | ✅ (16GB) | Apache 2.0 | ~$0.05/1M |
| InternVL3-78B | ~85 | ~93 | 72.2 | ~75 | 78B | ✅ (80GB+) | MIT | Free |
| InternVL3-8B | ~80 | ~92.7 | ~66 | ~72 | 8B | ✅ (16GB) | MIT | Free |
| Gemini 2.5 Pro | ~88 | ~96 | ~74 | ~80 | Unknown | ❌ | Commercial | $0.30/1M |
| GPT-5.2 | ~87 | ~95 | ~73 | ~78 | Unknown | ❌ | Commercial | ~$0.50/1M |
| Claude Sonnet 4 | ~83 | ~93 | ~70 | ~75 | Unknown | ❌ | Commercial | $0.30/1M |
| Gemini 2.5 Flash | ~82 | ~91 | ~68 | ~72 | Unknown | ❌ | Commercial | $0.03/1M |
| PaliGemma 2 | ~75 | ~85 | ~60 | ~65 | 3-28B | ✅ | Gemma License | Free |

### For Scientific Figure Interpretation Specifically

The key factors for our use case (neuroscience result figures):
1. **Axis reading accuracy** — Must correctly identify units, scales, ranges
2. **Legend-condition mapping** — Must link colors/styles to experimental conditions
3. **Quantitative estimation** — Must read approximate values from plots
4. **Error bar type identification** — SEM vs SD vs CI distinction matters
5. **Statistical annotation parsing** — *, **, n.s., p-values

**Best open-source**: Qwen3-VL (strongest on OCR, mathematical reasoning, chart understanding)
**Best proprietary**: Gemini 2.5 Pro (slightly higher on chart benchmarks, very long context)

### Recommendation

**Primary: Qwen3-VL-8B** (self-hosted on Mac Studio or GPU server)
- Fits in 16GB VRAM
- Apache 2.0 license — no data concerns
- 15-60% faster inference than Qwen2.5-VL
- Strong on OCR and mathematical reasoning

**Upgrade path: Qwen3-VL-72B** (self-hosted on GPU server)
- For complex multi-panel figures
- Requires 80GB+ VRAM (e.g., 2x A100 or H100)

**API fallback: Gemini 2.5 Flash**
- Best cost/performance ratio for API
- $0.03/1M tokens — affordable for batch processing
- But: data goes to Google (policy check needed for unpublished papers)

---

## 3. Reasoning LLMs (Argument Extraction & Prediction)

| Model | Scientific Reasoning | Structured Output | Cost | Self-Host | Notes |
|---|---|---|---|---|---|
| **Claude Sonnet 4** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | $3/1M in, $15/1M out | ❌ | Best at structured scientific reasoning, reliable YAML/JSON output |
| Claude Opus 4.6 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Higher | ❌ | More capable but slower, may be overkill |
| DeepSeek-R1 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Free (self-host) | ✅ (70B+) | Strong reasoning, chain-of-thought visible |
| Gemini 2.5 Pro | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | $0.30/1M | ❌ | Excellent on scientific benchmarks |
| GPT-5.2 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ~$5/1M | ❌ | Strong generalist, good at structured output |
| Qwen3-235B-A22B | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Free (self-host) | ✅ (needs MoE infra) | Apache 2.0, competitive with proprietary |

### Recommendation

**Primary: Claude Sonnet 4** — Exceptional at producing well-structured scientific analysis with reliable schema compliance. The prompt chaining approach benefits from Claude's consistency across multi-step reasoning.

**Self-hosted alternative: DeepSeek-R1-70B** — If data policy prohibits API usage for unpublished papers. Visible chain-of-thought is useful for debugging argument extraction quality.

---

## 4. Embedding Models

| Model | MTEB (avg) | MTEB (retrieval) | Dimensions | Context | License | Self-Host Cost |
|---|---|---|---|---|---|---|
| **BGE-M3** | 63.0 | ~65 | 1024 | 8192 | MIT | ~2GB VRAM |
| Qwen3-Embedding-8B | 70.58 | ~72 | 1024 | 8192 | Apache 2.0 | ~16GB VRAM |
| Voyage-3-large | 67.8 | ~70 | 1024-2048 | 32000 | Commercial | API only |
| Cohere embed-v4 | 65.2 | ~67 | variable | 128000 | Commercial | API only |
| NV-Embed-v2 | 69.32 | ~71 | 4096 | 32768 | CC-BY-NC | ~16GB VRAM |
| Jina v4 | ~65 | ~63 | 2048 | 8192 | CC-BY-NC | ~2GB VRAM |
| E5-Mistral | ~64 | ~66 | 4096 | 32768 | MIT | ~14GB VRAM |
| nomic-embed-text | ~60 | ~62 | 768 | 8192 | Apache 2.0 | ~1GB VRAM |

### Key Considerations for Scientific Paper Embedding

1. **Multilingual**: Papers cite Korean and English terms — need strong CJK support
2. **Long context**: Hypothesis descriptions can be 500+ tokens
3. **Domain specificity**: Fine-tuning on neuroscience corpus would help
4. **Hybrid retrieval**: Dense + sparse (BM25) improves recall for technical terms

### Recommendation

**Primary: BGE-M3** — Already deployed in CSNL infrastructure. Supports dense+sparse+multi-vector in single model. Strong multilingual (Korean+English+Japanese). MIT license.

**Upgrade candidate: Qwen3-Embedding-8B** — 12% higher MTEB scores. Apache 2.0 license. But requires significantly more GPU memory. Evaluate on actual CSNL queries before switching.

**For multimodal search (future)**: Voyage Multimodal 3.5 or Qwen3-VL-Embedding-2B — these can embed both text AND figure images into same vector space, enabling "find figures that look like this" queries.

---

## 5. Chart-Specific Models (Optional Specialized Tools)

| Model | Purpose | Strengths | Limitations |
|---|---|---|---|
| ChartVLM | Chart structural extraction | Trained specifically on charts | Older architecture |
| EvoChart | Real-world chart understanding | Self-training approach, handles noisy charts | Limited open-source availability |
| MatCha | Chart de-rendering | Pre-trained on chart reasoning | Google research, limited maintenance |
| TinyChart | Lightweight chart QA | Small model, fast | Lower accuracy on complex charts |
| UniChart | Universal chart understanding | Broad chart type coverage | Academic prototype |

### Recommendation

**Skip specialized chart models initially.** Qwen3-VL with well-crafted structured prompts should handle most neuroscience figures (line plots, bar charts, scatter plots, heatmaps). Add ChartVLM/EvoChart only if general VLM performance on figures is insufficient.

---

## Model Selection Decision Tree

```
Is the paper published or unpublished?
├── Published → API models OK
│   ├── Complex figures? → Gemini 2.5 Pro or Qwen3-VL-72B
│   └── Simple figures? → Qwen3-VL-8B (fastest)
└── Unpublished → Self-hosted only
    ├── Heavy math? → Nougat (parsing) + DeepSeek-R1 (reasoning)
    └── Standard format? → MinerU (parsing) + Qwen3-VL-8B (figures)
```
