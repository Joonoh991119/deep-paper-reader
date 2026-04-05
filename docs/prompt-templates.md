# Prompt Templates

All prompts used in the pipeline. Version-controlled for reproducibility.

---

## Stage 1: Initial Figure Description

### Prompt: `skeleton_figure_describe`

```
You are a scientific figure analyst. Given a figure image from a neuroscience paper, provide a brief structural description.

Focus on:
1. Chart type (bar chart, line plot, scatter plot, heatmap, brain map, etc.)
2. What appears to be on each axis
3. Number of conditions/groups visible
4. Whether there are error bars
5. Whether there are statistical annotations (*, **, n.s.)
6. Any notable patterns visible

Keep description under 100 words. Be factual, not interpretive.

Figure caption: {caption}
```

---

## Stage 2: Argument Extraction Chain

### Prompt 2a: `extract_background_claims`

```
You are analyzing the Introduction section of a neuroscience paper.

Paper title: {title}
Abstract: {abstract}
Introduction text: {introduction_text}

Extract all background claims made in the introduction. For each claim:
1. State the claim in one sentence
2. List the citations supporting it
3. Indicate whether this is widely accepted consensus or debated

Output as YAML:
```yaml
background_claims:
  - claim: "..."
    citations: ["Author Year", ...]
    is_consensus: true/false
    domain: "visual_working_memory" / "bayesian_inference" / etc.
```

Be exhaustive — extract every factual claim that sets up the paper's argument.
```

### Prompt 2b: `identify_research_gap`

```
Given the background claims from a neuroscience paper's introduction:

Background claims:
{background_claims_yaml}

Introduction text:
{introduction_text}

Identify the research gap — what is NOT known or NOT tested that motivates this paper.

Output as YAML:
```yaml
research_gap:
  statement: "No study has tested whether..."
  type: "unexplored" / "contradictory_findings" / "methodological_limitation" / "theoretical_gap"
  prior_attempts:
    - "Author (Year) tested X but not Y"
    - "..."
```

The gap should be specific enough that a reader could immediately understand what experiment would fill it.
```

### Prompt 2c: `extract_main_claim`

```
Given the research gap and the paper's abstract:

Research gap:
{gap_yaml}

Abstract:
{abstract}

Introduction text:
{introduction_text}

Extract the author's main claim — what they propose to show or demonstrate.

Output as YAML:
```yaml
main_claim:
  statement: "We propose/show/demonstrate that..."
  claim_type: "novel_mechanism" / "extends_existing" / "contradicts_existing" / "unifying_framework"
  theoretical_framework: "Bayesian observer model with..." / "Resource-rational framework" / etc.
```
```

### Prompt 2d: `formalize_hypotheses`

```
You are formalizing the testable hypotheses of a neuroscience paper.

Main claim: {main_claim_yaml}
Research gap: {gap_yaml}
Methods section: {methods_text}
Figure list: {figure_inventory}

For each hypothesis that the paper tests, formalize it with:

1. **Verbal statement**: Plain language
2. **Formal prediction**: Using variable names and direction
   - Format: "E[DV(condition_A)] > E[DV(condition_B)] when [moderator]"
3. **Predicted direction**: Which condition should be larger/smaller
4. **Key metric**: What is measured (e.g., "precision", "BOLD signal", "reaction time")
5. **Operationalization**: IV, DV, controls
6. **Relevant figures**: Which figures would show this result

Output as YAML:
```yaml
hypotheses:
  - id: "H1"
    verbal: "If X, then Y should..."
    formal: "E[metric(cond_A)] > E[metric(cond_B)] when Z"
    predicted_direction: "A > B"
    key_metric: "precision (1/circular_sd)"
    operationalization:
      independent_variable:
        name: "..."
        levels: ["...", "..."]
        type: "within" / "between"
      dependent_variable:
        name: "..."
        unit: "..."
      controls: ["...", "..."]
    relevant_figures: ["Fig2a", "Fig3"]
    alternative_if_false: "If H1 is rejected, this suggests..."
```

CRITICAL: Each hypothesis MUST have a directional prediction that can be checked against a figure.
If the paper implies a hypothesis but doesn't state it explicitly, formalize it anyway.
```

### Prompt 2e: `map_experimental_design`

```
Given the Methods section of a neuroscience paper:

Methods text: {methods_text}
Hypotheses: {hypotheses_yaml}

Map the experimental design for each experiment:

Output as YAML:
```yaml
experiments:
  - id: "Exp1"
    design: "2x3 within-subjects factorial"
    factors:
      - name: "distribution"
        levels: ["uniform", "clustered"]
        type: "within"
    n_participants: 24
    measure: "recall error (degrees)"
    statistical_tests: ["repeated-measures ANOVA", "BF10"]
    maps_to_hypotheses: ["H1"]
    relevant_figures: ["Fig2", "Fig3a"]
    paradigm: "delayed estimation task"
    stimuli: "oriented Gabor patches"
    procedure_summary: "..."
```

Be precise about:
- Exact factor levels (not just "high/low" but actual values)
- Sample size
- Statistical tests actually used
- Stimulus details
```

---

## Stage 3: Figure Interpretation

### Prompt 3a: `generate_prediction`

```
You are generating a prediction for what a scientific figure should show, based on the paper's hypotheses.

Hypothesis:
{hypothesis_yaml}

Experimental design:
{experiment_yaml}

Figure ID: {figure_id}
Figure caption: {caption}

Based on the hypothesis, predict what this figure should show:

Output as YAML:
```yaml
prediction:
  figure_id: "{figure_id}"
  from_hypothesis: "{hypothesis_id}"
  expected_chart_type: "line plot / bar chart / scatter / heatmap / ..."
  expected_x_axis:
    label: "..."
    values: ["...", "..."]
  expected_y_axis:
    label: "..."
    direction: "higher is better / lower is better"
  expected_groups:
    - label: "..."
      expected_trend: "..."
  expected_pattern: "Describe the key pattern in words"
  expected_interaction: "Describe any expected interaction"
  expected_statistics: "What statistical results would confirm this"
  prediction_confidence: 0.0-1.0
```

Think carefully: if H1 is true, what MUST the figure show?
```

### Prompt 3b: `interpret_figure`

```
You are a scientific figure analyst with expertise in neuroscience data visualization.

Given this figure from a neuroscience paper, analyze it in detail.

Caption: {caption}
Section context (surrounding paragraph): {context_paragraph}

Analyze the following — be precise and quantitative:

1. **AXES**
   - X-axis: label, unit, range, scale (linear/log/categorical)
   - Y-axis: label, unit, range, scale

2. **DATA ELEMENTS**
   - List each visual element (bars, lines, scatter points, etc.)
   - For each: color, line style (solid/dashed/dotted), marker shape
   - Map each to its legend label / experimental condition

3. **ERROR BARS**
   - Are there error bars? What type? (SEM, SD, 95% CI, or unspecified)

4. **STATISTICAL ANNOTATIONS**
   - Any significance markers (*, **, ***, n.s.)?
   - Between which comparisons?
   - Any p-values or effect sizes shown?

5. **QUANTITATIVE READINGS**
   - For each data element, estimate the key values from the plot
   - Format: condition X at level Y ≈ value

6. **MAIN TRENDS**
   - What are the dominant patterns?
   - Any interactions between conditions?
   - Anything unexpected or noteworthy?

Output as YAML:
```yaml
observation:
  figure_id: "{figure_id}"
  chart_type: "..."
  x_axis:
    label: "..."
    unit: "..." 
    range: "..."
    scale: "linear/log/categorical"
  y_axis:
    label: "..."
    unit: "..."
    range: "..."
    scale: "..."
  elements:
    - label: "..."
      color: "..."
      line_style: "..."
      marker: "..."
      estimated_values:
        - x: "..."
          y: 0.0
  error_bars:
    type: "SEM/SD/95%CI/unknown"
    present: true/false
  significance_markers:
    - comparison: "..."
      marker: "..."
      p_value: "..."
  main_trends:
    - "..."
```

IMPORTANT: Read values carefully. If you cannot read a value precisely, give your best estimate with ± range.
```

### Prompt 3c: `match_prediction_observation`

```
You are evaluating whether a scientific figure supports or contradicts a hypothesis.

Prediction (what the figure SHOULD show based on the hypothesis):
{prediction_yaml}

Observation (what the figure ACTUALLY shows from VLM analysis):
{observation_yaml}

Compare prediction to observation:

1. Does the observed pattern match the predicted direction?
2. Are the predicted conditions showing the expected relationship?
3. Is the expected interaction present?
4. Are there any surprises (patterns not predicted)?
5. Are there any concerns (e.g., overlapping error bars, weak effects)?

Output as YAML:
```yaml
match:
  figure_id: "{figure_id}"
  hypothesis_id: "{hypothesis_id}"
  match_result: "supported" / "partially_supported" / "not_supported" / "ambiguous"
  match_detail: "..."
  surprises:
    - "..."
  concerns:
    - "..."
  confidence: 0.0-1.0
```

Be rigorous. "Partially supported" means the direction is correct but the effect is weaker than expected or doesn't reach significance. "Ambiguous" means the figure cannot clearly distinguish between H and not-H.
```

---

## Stage 4: Discussion Analysis

### Prompt: `analyze_discussion`

```
You are critically analyzing the Discussion section of a neuroscience paper.

Paper context:
- Main claim: {main_claim}
- Hypotheses tested: {hypotheses_summary}
- Figure results: {prediction_match_summary}

Discussion text: {discussion_text}

Analyze:

1. **Author's interpretation**: What do they conclude? How strongly?
2. **Alternative explanations**: 
   - What alternatives do THEY mention?
   - What alternatives do they NOT mention but should have?
3. **Limitations**:
   - What do they acknowledge?
   - What important limitations do they miss?
4. **Broader connections**: How does this relate to existing work?
5. **Overall assessment**: Strength of evidence, novelty, rigor

Output as YAML following the DiscussionAnalysis schema.

Be constructively critical. Identify specific methodological concerns, not generic complaints.
For "unacknowledged limitations," think about what a rigorous reviewer would flag.
```

---

## Review Agent

### Prompt: `review_stage_output`

```
You are a quality review agent for an automated scientific paper reading pipeline.

You are evaluating the pipeline's output for one stage.

Stage: {stage_name}
Paper: {paper_title} ({paper_doi})

Original paper content (relevant sections):
{paper_sections}

Pipeline output:
{pipeline_output_yaml}

Scoring rubric:
{rubric}

Score each dimension 1-5:
- 5: Expert-level quality, no corrections needed
- 4: Good quality, minor improvements possible  
- 3: Adequate but needs improvement
- 2: Significant errors present
- 1: Wrong or misleading

Output as YAML:
```yaml
review:
  stage: "{stage_name}"
  paper_id: "{paper_doi}"
  scores:
    - dimension: "..."
      score: N
      justification: "..."
      correction: "..." # Only if score < 4
  overall_score: N.N
  critical_issues: ["..."]
  suggested_parameter_changes:
    - parameter: "..."
      current: "..."
      suggested: "..."
      reason: "..."
```

Be harsh but fair. Score 5 only when you would trust the output for a literature review.
```
