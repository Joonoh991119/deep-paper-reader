# Feedback Protocol

How the Deep Paper Reader learns and improves over time.

---

## Overview

The feedback loop operates at three levels:

1. **Automated Review Agent** — LLM-based critic that scores every output
2. **User Feedback** — Researcher corrections and ratings (async)
3. **Aggregate Metrics** — Statistical tracking across papers

---

## 1. Review Agent

### Architecture

The Review Agent is a separate LLM call that receives:
- The pipeline output (structured YAML)
- The original paper text (relevant sections)
- A rubric for each scoring dimension

It does NOT see its own prior outputs — this prevents confirmation bias.

### Scoring Rubric

#### Stage 1: Skeleton Quality

| Dimension | Score 5 | Score 3 | Score 1 |
|---|---|---|---|
| Section boundaries | All sections correctly identified, correct types | Most sections found, 1-2 misclassified | Major sections missing or wrong |
| Figure-caption pairing | All figures paired with correct captions | 1-2 mismatches | Multiple mismatches |
| Reading order | Text flows naturally, multi-column handled | Minor order issues | Major scrambling |
| Equation completeness | All equations as complete LaTeX | Minor truncation | Equations missing or broken |

#### Stage 2: Argument Quality

| Dimension | Score 5 | Score 3 | Score 1 |
|---|---|---|---|
| Gap identification | Gap is specific, correctly inferred from intro | Gap is vague but in right direction | Wrong gap or missing |
| Hypothesis formality | Testable prediction with direction, metric, conditions | Has prediction but missing components | No clear prediction |
| Operationalization | IV/DV/controls correctly mapped to methods | Partially correct | Wrong mappings |
| Design mapping | Factorial structure correct, N accurate | Minor errors | Wrong design |

#### Stage 3: Figure Interpretation

| Dimension | Score 5 | Score 3 | Score 1 |
|---|---|---|---|
| Axes identification | Both axes correct (label, unit, range) | One axis wrong or unit missing | Both wrong |
| Legend mapping | All conditions correctly linked | 1-2 errors | Major confusion |
| Quantitative reading | Values within 10% of actual | Values within 30% | Off by >30% or wrong |
| Error bar type | Correctly identified (SEM/SD/CI) | Type guessed but may be wrong | Not attempted |
| Prediction match | Match judgment logically sound | Match judgment plausible but weak | Logically wrong |

#### Stage 4: Discussion Quality

| Dimension | Score 5 | Score 3 | Score 1 |
|---|---|---|---|
| Author interpretation | Accurately captures author's main conclusion | Partially accurate | Misrepresents |
| Alternative explanations | Identifies alternatives authors missed | Only restates what authors said | Nothing useful |
| Limitations | Identifies real methodological issues | Generic limitations | Nothing specific |

### Review Agent Prompt Template

```
You are a scientific review agent evaluating the quality of an automated paper reading pipeline.

You will be given:
1. The original paper content (relevant sections)
2. The pipeline's structured output
3. A scoring rubric

Your task: Score each dimension 1-5 and provide brief justification.

Rules:
- Be harsh. Score 3 is "adequate but could be better."
- Score 5 only when the output matches expert-level reading.
- Score 1 when the output is wrong or misleading.
- Provide specific corrections when scoring below 3.

Output format:
```yaml
review:
  stage: "stage2"
  paper_id: "..."
  scores:
    - dimension: "gap_identification"
      score: 4
      justification: "Gap correctly identified but phrased too broadly"
      correction: "Gap should specify 'naturalistic distribution conditions' not just 'different conditions'"
    - dimension: "hypothesis_formality"
      score: 3
      justification: "Prediction direction correct but metric not operationalized"
      correction: "Should specify 'circular SD of recall error' not just 'error'"
  overall_score: 3.5
  critical_issues: ["Hypothesis H2 maps to wrong figure"]
  suggested_parameter_changes:
    - parameter: "stage2.hypothesis_formality"
      current: "semi-formal"
      suggested: "formal"
      reason: "Predictions too vague for accurate figure prediction"
```
```

---

## 2. User Feedback

### Feedback Types

| Type | When Used | Data Collected |
|---|---|---|
| **Rating** | After reading pipeline output | 1-5 score per stage |
| **Correction** | When output is wrong | Field name, expected value, actual value |
| **Comment** | General observations | Free text |
| **Rejection** | Output is unusable | Reason for rejection |
| **Approval** | Output is excellent | Implicit (no correction needed) |

### Feedback Collection Points

1. **Post-skeleton** (optional): "Did the parser correctly identify all figures?"
2. **Post-argument** (recommended): "Are the hypotheses correctly formalized?"
3. **Post-figure** (critical): "Are the figure interpretations accurate?"
4. **Post-discussion** (optional): "Are the critical gaps valid?"

### Feedback Aggregation Rules

```python
def should_rerun_stage(scores: list[int], threshold: float = 2.5) -> bool:
    """Decide whether to re-run a stage based on feedback scores."""
    avg_score = sum(scores) / len(scores)
    return avg_score < threshold

def should_adjust_parameter(param_name: str, feedback_log: list) -> bool:
    """Decide whether to adjust a parameter based on feedback pattern."""
    recent = feedback_log[-10:]  # Last 10 papers
    relevant = [f for f in recent if param_name in f.suggested_changes]
    return len(relevant) >= 3  # At least 3 suggestions in last 10 papers
```

---

## 3. Parameter Adjustment Rules

### Automatic Adjustments

| Trigger | Parameter | Adjustment |
|---|---|---|
| Avg figure score < 3.0 (last 5 papers) | `stage3.vlm_temperature` | Decrease by 0.05 |
| Avg figure score < 3.0 (last 5 papers) | `stage1.figure_resolution` | Increase by 50 DPI |
| Avg argument score < 3.0 | `stage2.prompt_chain_depth` | Increase by 1 step |
| Reading order score < 2.5 | `stage1.chunk_size` | Decrease by 128 tokens |
| Prediction match score < 2.5 | `stage3.prediction_specificity` | Switch to "quantitative" |
| Quantitative reading error > 20% | `stage3.num_quantitative_reads` | Increase by 2 |

### Manual Adjustments (via config)

Users can override any parameter in `configs/pipeline_config.yaml`.

### Adjustment Logging

Every parameter change is logged:

```yaml
adjustment_log:
  - timestamp: "2026-04-05T14:30:00Z"
    parameter: "stage3.vlm_temperature"
    old_value: 0.15
    new_value: 0.10
    trigger: "avg_figure_score < 3.0 over last 5 papers"
    papers_affected: ["doi:1", "doi:2", "doi:3", "doi:4", "doi:5"]
```

---

## 4. Periodic Review Cycle

### Weekly
- Review aggregate scores by stage
- Identify consistent failure patterns
- Flag papers that scored < 2.5 overall for manual review

### Monthly
- Analyze feedback patterns → update prompt templates
- Evaluate whether model upgrades are needed
- Re-run worst-performing papers with updated parameters to measure improvement

### Quarterly
- Benchmark against manually-read papers (gold standard)
- Consider model swaps if better alternatives available
- Update model-comparison.md with new benchmark data

---

## 5. Gold Standard Creation

To evaluate the pipeline, we need gold standard annotations:

1. **Select 10 papers** from GRM archive (diverse: behavioral, fMRI, computational)
2. **Expert annotation**: 2 researchers independently annotate:
   - Correct hypotheses and operationalizations
   - Correct figure interpretations (axes, values, trends)
   - Correct prediction-observation matches
3. **Inter-annotator agreement**: Compute Cohen's kappa on key fields
4. **Pipeline evaluation**: Compare pipeline output to gold standard
5. **Metrics**: Per-field accuracy, F1 for hypothesis extraction, MAE for quantitative readings
