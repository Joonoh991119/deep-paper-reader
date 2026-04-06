# Deep Paper Reader (DPR)

**Comprehension-Driven Scientific Paper Parsing & Embedding Pipeline**

> A multi-stage reading system that replicates the cognitive workflow of an expert scientific reviewer — not just parsing, but *understanding* papers through structured argument extraction, hypothesis formalization, figure prediction-verification, and critical discussion analysis.

## Why This Exists

Most paper-parsing systems stop at layout segmentation + OCR. This project implements **comprehension-driven parsing**: the system builds a mental model of the paper's argument structure, then uses that model to *predict and verify* figure content. This closes the loop between text understanding and visual interpretation.

**Target domain**: Neuroscience journals (initially), expandable to broader scientific literature.

**Developed for**: CSNL (Cognitive and Systems Neuroscience Lab), Seoul National University

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Deep Paper Reader Pipeline                    │
├──────────┬──────────┬───────────┬──────────┬───────────────────┤
│ Stage 1  │ Stage 2  │ Stage 3   │ Stage 4  │ Feedback Loop     │
│ Skeleton │ Argument │ Figure    │ Critical │ (Continuous       │
│ Scan     │ Extract  │ Deep Read │ Discuss. │  Improvement)     │
│ (~30s)   │ (~60s)   │ (~120s)   │ (~30s)   │                   │
├──────────┼──────────┼───────────┼──────────┼───────────────────┤
│ Layout   │ Intro    │ Predict   │ Author   │ User feedback     │
│ detect   │ parse    │ from H    │ interp.  │ Review agent      │
│ Figure   │ Gap/Claim│ VLM axes  │ Alt.     │ Reading order     │
│ extract  │ Hypothe- │ colors    │ explan.  │ Chunk size        │
│ OCR/math │ sis form │ Pred vs   │ Limits   │ Prediction        │
│ Abstract │ Methods  │ Observe   │ Gaps     │ quality           │
│ overview │ map      │ match     │          │                   │
└──────────┴──────────┴───────────┴──────────┴───────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │ Structured Embedding│
                    │ (Multi-level index) │
                    └────────────────────┘
```

---

## Stage Details & Model Alternatives

### Stage 1: Skeleton Scan (논문 골격 파악)

**Goal**: Rapid structural grasping — title, abstract, graphical abstract, key figures in ~30 seconds.

| Component | Primary Choice | Alternative 1 | Alternative 2 | Alternative 3 | Notes |
|---|---|---|---|---|---|
| **Layout Detection** | DocLayout-YOLO | LayoutLMv3 (fine-tuned) | DiT (Document Image Transformer) | YOLO-Doc | DocLayout-YOLO achieves best mAP on academic papers in PDF-Extract-Kit benchmarks |
| **PDF → Structured Text** | MinerU (magic-pdf) | Nougat (Meta) | Marker | Docling (IBM) | MinerU scores 86.2 on OmniDocBench v1.5; Nougat excels at math-heavy LaTeX preservation |
| **Figure Extraction** | MinerU built-in | PDFFigures 2.0 (AllenAI) | DeepFigures | GROBID | MinerU extracts figure+caption pairs natively; PDFFigures 2.0 is more mature for linking |
| **Formula Recognition** | UniMERNet | Mathpix (commercial) | Pix2Tex | LaTeX-OCR | UniMERNet achieves 0.968 CDM (comparable to Mathpix 0.951) |
| **Table Recognition** | StructEqTable | TableMaster | TATR (Table Transformer) | PaddleOCR-Table | StructEqTable outputs HTML/LaTeX directly |
| **OCR Engine** | PaddleOCR | Tesseract 5.5 | EasyOCR | TrOCR | PaddleOCR supports 84+ languages with strong CJK performance |
| **Initial Figure Description** | Qwen3-VL-8B | Qwen2.5-VL-72B | InternVL3-8B | Gemini 2.5 Flash | Quick visual triage — does not need deep interpretation yet |

**Output**: `PaperSkeleton` schema (see `docs/schemas.md`)

---

### Stage 2: Argument Extraction (논증 구조 파악)

**Goal**: From Introduction + Methods, extract: background → gap → claim → hypotheses → operationalization

| Component | Primary Choice | Alternative 1 | Alternative 2 | Notes |
|---|---|---|---|---|
| **Argument Structure LLM** | Claude Sonnet 4 (API) | DeepSeek-R1 (self-hosted) | Gemini 2.5 Pro | Needs strong scientific reasoning + structured output |
| **Hypothesis Formalization** | Claude Sonnet 4 | GPT-5.2 | Qwen3-235B (self-hosted) | Must formalize verbal hypotheses into testable predictions |
| **Methods → Design Mapping** | Same as above | — | — | Chain-of-thought prompt, not separate model |

**Critical design decision**: This stage uses **prompt chaining**, not single-shot. The prompt chain is:

```
1. Extract background claims + citations
2. Identify research gap (what is NOT known)
3. Extract author's main claim / thesis
4. Formalize each hypothesis with:
   - Verbal statement
   - Formal prediction (direction, metric, conditions)
   - Mapping to expected figures
5. Map methods → experimental design structure
   - IV, DV, controls, N, statistical tests
```

**Output**: `ArgumentStructure` + `HypothesisSet` + `ExperimentalDesign` schemas

---

### Stage 3: Figure Deep Interpretation (수리적 해석)

**Goal**: Two parallel processes — predict expected patterns from hypotheses, then verify against actual figures.

| Component | Primary Choice | Alternative 1 | Alternative 2 | Alternative 3 | Notes |
|---|---|---|---|---|---|
| **Chart/Figure VLM** | Qwen3-VL-72B | InternVL3-78B | Gemini 2.5 Pro | GPT-5.2 | Must extract axes, units, legend, data trends quantitatively |
| **Prediction Generation** | Claude Sonnet 4 | DeepSeek-R1 | Gemini 2.5 Pro | — | Top-down: given H, predict what figure SHOULD show |
| **Prediction-Observation Match** | Claude Sonnet 4 | — | — | — | Multi-step logical comparison requiring scientific reasoning |
| **Chart-specific model** | ChartVLM / EvoChart | MatCha | TinyChart | UniChart | Specialized for chart structural extraction |

**The key innovation**: Before VLM interprets a figure, the system generates a **prediction** from Stage 2 hypotheses:

```yaml
# Example prediction for Fig2a
prediction:
  from_hypothesis: H1
  expected_chart_type: "line plot or bar chart"
  expected_x_axis: "set size (2, 4, 6)"
  expected_y_axis: "recall error (degrees) or precision"
  expected_pattern: "clustered < uniform error, diverging at higher set sizes"
  expected_interaction: "lines should diverge as set_size increases"
```

Then the VLM interprets the figure with a **structured prompt** that extracts:
1. Axes (what, unit, range)
2. Data elements (bars/lines/scatter — color, style, legend mapping)
3. Error bars (type: SEM, SD, 95% CI)
4. Statistical annotations (*, **, n.s.)
5. Quantitative estimates (read values off the plot)
6. Main trends and interactions

Finally, the system **matches prediction vs. observation** and flags surprises.

**Output**: `FigureAnalysis` + `PredictionMatch` schemas

---

### Stage 4: Discussion Critical Reading (비판적 읽기)

**Goal**: Brief critical assessment of discussion section.

| Component | Primary Choice | Alternative 1 | Notes |
|---|---|---|---|
| **Critical Analysis LLM** | Claude Sonnet 4 | DeepSeek-R1 | Same model as Stage 2 for consistency |

Extracts:
- Author's own interpretation
- Alternative explanations mentioned (and not mentioned)
- Limitations acknowledged
- Critical gaps the authors missed
- Connection to broader field

**Output**: `DiscussionAnalysis` schema

---

## Embedding Strategy

**Do NOT embed the paper as flat chunks.** Embed the structured outputs at multiple levels:

| Level | What's Embedded | Embedding Model Options | Use Case |
|---|---|---|---|
| L0: Paper identity | title + abstract + main claim | BGE-M3 / Voyage-3-large | "Find papers about X" |
| L1: Hypothesis | Each hypothesis + experimental context | BGE-M3 / Qwen3-Embedding-8B | "Papers testing efficient coding" |
| L2: Figure analysis | Each figure interpretation + axes/metrics | BGE-M3 + multimodal (Voyage-MM-3.5) | "Figures showing set-size effects" |
| L3: Prediction-match | Prediction vs observation pairs | BGE-M3 | "Papers where H was surprised" |
| L4: Critical analysis | Discussion gaps + limitations | BGE-M3 | "Papers with weak controls for X" |

### Embedding Model Alternatives

| Model | MTEB Score | Dimensions | Context | License | Best For |
|---|---|---|---|---|---|
| **BGE-M3** (primary) | 63.0 | 1024 | 8192 | MIT | Multilingual, hybrid dense+sparse, self-hosted |
| Qwen3-Embedding-8B | 70.58 (multilingual) | 1024 | 8192 | Apache 2.0 | Highest open-source MTEB, multilingual |
| Voyage-3-large | 67.8 | 1024-2048 | 32000 | Commercial | Best commercial retrieval quality |
| Cohere embed-v4 | 65.2 | variable | 128000 | Commercial | Long-context, enterprise |
| NV-Embed-v2 | 69.32 | 4096 | 32768 | CC-BY-NC | Research-only, highest English retrieval |
| Jina v4 | ~65 | 2048 | 8192 | CC-BY-NC (weights) | Task-specific LoRA adapters |
| E5-Mistral | ~64 | 4096 | 32768 | MIT | Good balance, open weights |
| nomic-embed-text | ~60 | 768 | 8192 | Apache 2.0 | Fully open (weights+data+code), lightweight |

**Recommendation**: Start with **BGE-M3** (already in CSNL stack) for consistency, evaluate **Qwen3-Embedding-8B** as upgrade path given its superior MTEB scores and Apache 2.0 license.

---

## Feedback Loop & Continuous Improvement

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Feedback Loop System                 │
│                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │ User     │──▶│ Feedback     │──▶│ Parameter   │ │
│  │ Feedback │   │ Aggregator   │   │ Adjuster    │ │
│  └──────────┘   └──────┬───────┘   └──────┬──────┘ │
│                        │                   │        │
│  ┌──────────┐   ┌──────▼───────┐   ┌──────▼──────┐ │
│  │ Review   │──▶│ Quality      │──▶│ Config      │ │
│  │ Agent    │   │ Scorer       │   │ Updater     │ │
│  └──────────┘   └──────────────┘   └─────────────┘ │
└─────────────────────────────────────────────────────┘
```

### What the Review Agent Critiques

The Review Agent is an LLM-based critic that evaluates each pipeline output:

1. **Reading Order Assessment**
   - Did Stage 1 correctly identify section boundaries?
   - Were multi-column layouts parsed in correct reading order?
   - Score: 1-5 per paper

2. **Parsing Chunk Quality**
   - Are text chunks semantically coherent?
   - Do figure-caption pairs match correctly?
   - Are equations complete (not split across chunks)?
   - Score: 1-5 per paper

3. **Argument Extraction Quality**
   - Is the research gap correctly identified?
   - Are hypotheses logically derived from the claimed gap?
   - Are operationalizations faithful to the verbal hypotheses?
   - Score: 1-5 per component

4. **Prediction Soundness**
   - Given H1, is the predicted figure pattern logically valid?
   - Does the prediction specify direction, metric, and conditions?
   - Would an expert reviewer agree with this prediction?
   - Score: 1-5 per prediction

5. **Figure Interpretation Accuracy**
   - Are axes correctly identified (label, unit, range)?
   - Are legend entries correctly mapped to conditions?
   - Are quantitative readings reasonable?
   - Are error bar types correctly identified?
   - Score: 1-5 per figure

6. **Prediction-Match Validity**
   - Is the match/mismatch judgment logically sound?
   - Are "surprises" genuinely surprising or just under-specified predictions?
   - Score: 1-5 per match

### User Feedback Interface

Users (researchers) can provide feedback at each stage:

```yaml
user_feedback:
  paper_id: "doi:10.1234/example"
  stage: "stage3_figure"
  figure_id: "Fig2a"
  feedback_type: "correction"  # or "rating", "comment", "rejection"
  content:
    field: "y_axis"
    expected: "precision (1/circular_sd)"
    actual_output: "recall error (degrees)"
    comment: "The model confused error with precision — inverse relationship"
  rating: 2  # 1-5
```

### Adjustable Parameters (via feedback)

| Parameter | Default | Adjustment Range | Adjusted By |
|---|---|---|---|
| `stage1.chunk_size` | 512 tokens | 256-2048 | Parsing quality score |
| `stage1.figure_resolution` | 300 DPI | 150-600 | Figure interpretation accuracy |
| `stage2.prompt_chain_depth` | 5 steps | 3-8 | Argument extraction quality |
| `stage2.hypothesis_formality` | "semi-formal" | casual/semi-formal/formal | User preference |
| `stage3.vlm_temperature` | 0.1 | 0.0-0.5 | Figure interpretation accuracy |
| `stage3.prediction_specificity` | "directional" | directional/quantitative/both | Prediction soundness |
| `stage3.num_quantitative_reads` | 3 per figure | 1-10 | Figure accuracy score |
| `stage4.critical_depth` | "moderate" | brief/moderate/deep | User preference |
| `embedding.level_weights` | [0.3, 0.25, 0.25, 0.1, 0.1] | adjustable | Retrieval relevance |

### Feedback-Driven Learning Loop

```
1. Process paper → generate structured outputs
2. Review Agent scores each output (automated)
3. User provides feedback (optional, async)
4. Feedback Aggregator combines scores
5. If score < threshold:
   a. Identify lowest-scoring component
   b. Adjust corresponding parameters
   c. Re-run that stage (optional)
6. Log all feedback for periodic prompt refinement
7. Monthly: analyze feedback patterns → update prompt templates
```

---

## Project Structure

```
deep-paper-reader/
├── README.md                      # This file
├── docs/
│   ├── schemas.md                 # All output schemas (YAML)
│   ├── model-comparison.md        # Detailed model benchmarks
│   ├── prompt-templates.md        # All prompt chains
│   ├── feedback-protocol.md       # User feedback specification
│   └── roadmap.md                 # Phase-by-phase implementation plan
├── configs/
│   ├── pipeline_config.yaml       # Main pipeline configuration
│   ├── model_registry.yaml        # Model alternatives registry
│   └── feedback_thresholds.yaml   # Feedback loop parameters
├── src/
│   ├── stage1_skeleton/           # PDF parsing, layout, figure extraction
│   ├── stage2_argument/           # Argument extraction, hypothesis formalization
│   ├── stage3_figure/             # VLM figure interpretation, prediction matching
│   ├── stage4_discussion/         # Critical discussion analysis
│   ├── feedback_loop/             # Review agent, user feedback, parameter adjustment
│   └── embeddings/                # Multi-level structured embedding
├── tests/                         # Test papers and expected outputs
├── scripts/                       # Utility scripts
└── pyproject.toml                 # Project dependencies
```

---

## Quick Start (planned)

```bash
# Install
pip install deep-paper-reader

# Process a single paper
dpr process paper.pdf --output-dir ./output --config configs/pipeline_config.yaml

# Process with feedback
dpr process paper.pdf --enable-review-agent --enable-user-feedback

# Batch process
dpr batch ./papers/ --output-dir ./output --parallel 4
```

---

## Requirements

- Python 3.10+
- GPU: NVIDIA with ≥24GB VRAM (for local VLM inference) or API access
- Storage: ~10GB for model weights (if self-hosting)
- API keys (if using cloud models): Anthropic, OpenAI, or Google

---

## Confirmed Decisions (2026-04-06)

| Decision | Choice | Rationale |
|---|---|---|
| **VLM for figures** | Qwen3-VL-8B (local) | No data leaves lab. Upgrade to 72B on GPU server later. |
| **Embedding model** | BGE-M3 (keep) | Already in CSNL stack. No change needed. |
| **API policy** | Free only, prefer local | DeepSeek free API + Gemini Flash free tier as fallbacks. No paid APIs. |
| **Feedback UI** | Web interface (FastAPI/Streamlit) | Build user feedback UI for researcher corrections. |
| **Paper source** | Zotero DB first | Start with J's Zotero library. Zotero API integration included. |
| **Reasoning LLM** | DeepSeek-R1 (local or free API) | Free, visible chain-of-thought, strong math reasoning. |
| **Review Agent** | DeepSeek-R1 (same) | Consistency with reasoning model, no cost. |

---

## Implementation Roadmap

| Phase | Duration | Deliverables | Dependencies |
|---|---|---|---|
| **A: Skeleton Pipeline** | 2 weeks | PDF → structured skeleton + figure extraction | MinerU setup on Mac Studio |
| **B: Argument Extraction** | 2 weeks | Prompt chains for hypothesis formalization | Claude API access, 5 annotated papers |
| **C: Figure Deep Read** | 3 weeks | VLM interpretation + prediction matching loop | VLM deployment (Qwen3-VL or API) |
| **D: Embedding Integration** | 1 week | Multi-level embedding into LightRAG/BGE-M3 | Existing CSNL infra |
| **E: Feedback Loop** | 2 weeks | Review agent + parameter adjustment | Stages A-D complete |
| **F: Evaluation** | 1 week | Benchmark on 20 GRM papers, compare to manual reading | Researcher volunteers |

---

## License

MIT License — for CSNL internal use and open-source contribution.

---

## References

- MinerU: [github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU)
- PDF-Extract-Kit: [github.com/opendatalab/PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit)
- Qwen3-VL: [github.com/QwenLM/Qwen3-VL](https://github.com/QwenLM/Qwen3-VL)
- InternVL3: [arxiv.org/abs/2504.10479](https://arxiv.org/abs/2504.10479)
- BGE-M3: [huggingface.co/BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)
- ChartVLM/ChartX: [arxiv.org/abs/2402.12185](https://arxiv.org/abs/2402.12185)
- EvoChart: [ojs.aaai.org/index.php/AAAI/article/view/32383](https://ojs.aaai.org/index.php/AAAI/article/view/32383)
- SciEx Framework: [arxiv.org/abs/2512.10004](https://arxiv.org/abs/2512.10004)
- OmniDocBench: CVPR 2025
