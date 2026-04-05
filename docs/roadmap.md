# Implementation Roadmap

---

## Phase A: Skeleton Pipeline (Week 1-2)

### Goals
- PDF → structured skeleton with figure extraction
- Test on 10 papers from GRM archive

### Tasks
1. Set up MinerU on Mac Studio (or GPU server)
2. Build `PaperSkeleton` parser that wraps MinerU output
3. Add Qwen3-VL-8B for initial figure descriptions
4. Build figure-caption linking logic
5. Create section type classifier (intro/methods/results/discussion)
6. Write tests with 3 manually verified papers

### Deliverables
- `src/stage1_skeleton/parser.py` — MinerU wrapper
- `src/stage1_skeleton/figure_extractor.py` — Figure-caption pairing
- `src/stage1_skeleton/section_classifier.py` — Section type detection
- `src/stage1_skeleton/vlm_describer.py` — Quick VLM figure triage
- `tests/test_stage1.py` — Verified against 3 gold-standard papers

### Dependencies
- MinerU installed and working
- Qwen3-VL-8B accessible (local or API)
- 10 GRM papers as test corpus

---

## Phase B: Argument Extraction (Week 3-4)

### Goals
- Prompt chains for hypothesis formalization
- Validated on 5 manually annotated papers

### Tasks
1. Design prompt chain (5 steps) for argument extraction
2. Implement structured output parser (YAML from LLM)
3. Build hypothesis formalization logic
4. Build experimental design mapper
5. Manual annotation of 5 papers (gold standard)
6. Evaluate prompt chain accuracy against gold standard
7. Iterate on prompts until >80% field accuracy

### Deliverables
- `src/stage2_argument/argument_extractor.py` — Prompt chain orchestrator
- `src/stage2_argument/hypothesis_formalizer.py` — H → formal prediction
- `src/stage2_argument/design_mapper.py` — Methods → experimental design
- `src/stage2_argument/prompts/` — All prompt templates (versioned)
- `tests/test_stage2.py` — Against 5 annotated papers

### Dependencies
- Claude Sonnet 4 API access
- 5 papers with manual argument annotations
- Stage 1 outputs as input

---

## Phase C: Figure Deep Interpretation (Week 5-7)

### Goals
- VLM figure interpretation with prediction-matching loop
- This is the hardest and most novel component

### Tasks
1. Build prediction generator (H → expected figure pattern)
2. Design structured VLM prompt for figure analysis
3. Implement axis/legend/data extraction from VLM output
4. Build prediction-observation matcher
5. Handle subfigures and multi-panel figures
6. Test on 20+ figures across 10 papers
7. Iterate on VLM prompt until quantitative readings are within 15%

### Deliverables
- `src/stage3_figure/prediction_generator.py` — H → expected pattern
- `src/stage3_figure/vlm_interpreter.py` — Structured VLM figure analysis
- `src/stage3_figure/prediction_matcher.py` — Predict vs. observe comparison
- `src/stage3_figure/prompts/` — VLM prompt templates
- `tests/test_stage3.py` — Against manually verified figure interpretations

### Dependencies
- Stage 2 outputs (hypotheses) as input
- VLM running reliably (Qwen3-VL-8B minimum)
- 20+ neuroscience figures as test corpus

### Risk
- This is the highest-risk phase. VLM figure interpretation may not achieve 
  sufficient accuracy on first iteration. Plan for 2+ rounds of prompt refinement.

---

## Phase D: Embedding Integration (Week 8)

### Goals
- Multi-level structured embedding into LightRAG/BGE-M3

### Tasks
1. Define embedding schema for each level (L0-L4)
2. Build embedder that converts structured outputs → vectors
3. Integrate with existing LightRAG infrastructure
4. Build query interface (`csnl.search` compatible)
5. Test retrieval quality with 10 sample queries

### Deliverables
- `src/embeddings/multi_level_embedder.py` — Structured → vectors
- `src/embeddings/query_interface.py` — Search across levels
- Integration with `csnl.search` MCP tool

### Dependencies
- BGE-M3 running (already in CSNL stack)
- LightRAG infrastructure accessible
- Stage 1-3 outputs as input

---

## Phase E: Feedback Loop (Week 9-10)

### Goals
- Review agent + parameter adjustment system

### Tasks
1. Build Review Agent with scoring rubric
2. Implement feedback aggregator
3. Build parameter adjustment logic
4. Create feedback logging system
5. Test feedback loop on 5 papers (score → adjust → re-run → measure improvement)

### Deliverables
- `src/feedback_loop/review_agent.py` — LLM-based critic
- `src/feedback_loop/feedback_aggregator.py` — Score aggregation
- `src/feedback_loop/parameter_adjuster.py` — Automatic tuning
- `src/feedback_loop/feedback_logger.py` — Logging system
- `configs/feedback_thresholds.yaml` — Threshold configuration

### Dependencies
- All stages (1-4) operational
- Claude Sonnet 4 API for review agent

---

## Phase F: Evaluation & Benchmarking (Week 11)

### Goals
- Benchmark on 20 GRM papers
- Compare pipeline output to manual expert reading

### Tasks
1. Process 20 papers through full pipeline
2. Researcher volunteers rate output quality
3. Compare to manual reading notes (where available)
4. Calculate per-stage accuracy metrics
5. Identify systematic failure patterns
6. Document results and improvement priorities

### Deliverables
- `docs/evaluation_results.md` — Benchmark results
- `docs/known_limitations.md` — Systematic failure patterns
- Updated `configs/pipeline_config.yaml` with tuned parameters

### Dependencies
- All stages + feedback loop operational
- 2-3 researcher volunteers for evaluation
- 20 GRM papers selected

---

## Future Phases (post-v1.0)

### Phase G: User Feedback UI
- FastAPI web interface for researcher feedback
- Per-figure, per-hypothesis correction interface
- Dashboard showing pipeline improvement over time

### Phase H: Multimodal Embedding
- Add figure image embedding (Voyage-MM-3.5 or Qwen3-VL-Embedding)
- Enable "find figures that look like this" queries
- Cross-modal search: text query → relevant figures

### Phase I: Active Learning
- Identify papers where pipeline is least confident
- Prioritize these for user feedback
- Fine-tune prompts on corrected outputs

### Phase J: Domain Expansion
- Extend to psychology, cognitive science, computational neuroscience
- Add journal-specific prompt variants
- Build domain vocabulary expansion from processed papers
