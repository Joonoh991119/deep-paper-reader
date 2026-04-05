# Output Schemas

All pipeline outputs are structured YAML/JSON. This document defines every schema.

---

## Stage 1: PaperSkeleton

```yaml
paper_skeleton:
  # Metadata
  doi: str                          # e.g., "10.1038/s41593-024-01234-5"
  title: str
  authors:
    - name: str
      affiliation: str
  journal: str
  year: int
  paper_type: enum                  # "empirical" | "computational" | "review" | "methods" | "case_study"

  # Abstract
  abstract: str                     # Full abstract text
  keywords: list[str]               # Extracted or provided keywords

  # Graphical Abstract (if present)
  graphical_abstract:
    present: bool
    image: bytes | null
    vlm_description: str | null     # VLM-generated description

  # Section Map
  sections:
    - id: str                       # "sec_intro", "sec_methods", etc.
      title: str
      start_page: int
      type: enum                    # "introduction" | "methods" | "results" | "discussion" | "supplementary"

  # Figure Inventory
  figures:
    - id: str                       # "Fig1", "Fig1a", "Fig2"
      image: bytes                  # Extracted figure image
      caption: str                  # Full caption text
      section_context: str          # Which section references this figure
      vlm_initial_description: str  # Quick VLM description
      has_subfigures: bool
      subfigures:                   # If has_subfigures
        - id: str                   # "Fig1a", "Fig1b"
          image: bytes
          caption_segment: str

  # Table Inventory
  tables:
    - id: str                       # "Table1", "Table2"
      content_html: str             # Table as HTML
      caption: str
      section_context: str

  # Equations
  equations:
    - id: str                       # "Eq1", "Eq2"
      latex: str                    # LaTeX representation
      context: str                  # Surrounding text

  # Quick Stats
  num_figures: int
  num_tables: int
  num_equations: int
  num_experiments_estimated: int    # Rough estimate from skeleton
  total_pages: int
```

---

## Stage 2: ArgumentStructure

```yaml
argument_structure:
  paper_id: str                     # Links to paper_skeleton.doi

  # Background Claims
  background_claims:
    - claim: str                    # "Visual working memory has limited capacity"
      citations: list[str]          # ["Luck & Vogel 1997", "Zhang & Luck 2008"]
      is_consensus: bool            # Is this widely accepted?
      domain: str                   # "visual_working_memory", "bayesian_inference"

  # Research Gap
  research_gap:
    statement: str                  # "No study has tested whether X under condition Y"
    type: enum                      # "unexplored" | "contradictory_findings" | "methodological_limitation" | "theoretical_gap"
    prior_attempts: list[str]       # What has been tried before

  # Author's Main Claim
  main_claim:
    statement: str                  # "We propose that Z explains the gap"
    claim_type: enum                # "novel_mechanism" | "extends_existing" | "contradicts_existing" | "unifying_framework"
    theoretical_framework: str      # "Bayesian observer model with efficient coding"

  # Hypotheses
  hypotheses:
    - id: str                       # "H1"
      verbal: str                   # "If efficient coding governs VWM, then..."
      formal: str                   # "E[precision(cond_A)] > E[precision(cond_B)] when set_size > 4"
      predicted_direction: str      # "A > B"
      is_directional: bool
      relevant_figures: list[str]   # ["Fig2a", "Fig3"]
      key_metric: str               # "precision (1/circular_sd)"
      operationalization:
        independent_variable:
          name: str                 # "stimulus distribution"
          levels: list[str]         # ["uniform", "clustered"]
          type: enum                # "within" | "between"
        dependent_variable:
          name: str                 # "recall error"
          unit: str                 # "degrees (circular SD)"
          measurement: str          # "continuous adjustment response"
        controls: list[str]         # ["set size matched", "exposure duration constant"]
      alternative_if_false: str     # "If H1 is rejected, this suggests..."

  # Experimental Design
  experiments:
    - id: str                       # "Exp1"
      design: str                   # "2x3 within-subjects factorial"
      factors:
        - name: str                 # "distribution"
          levels: list[str]         # ["uniform", "clustered"]
          type: enum                # "within" | "between"
      n_participants: int           # 24
      measure: str                  # "recall error (degrees)"
      statistical_tests: list[str]  # ["repeated-measures ANOVA", "BF10"]
      maps_to_hypotheses: list[str] # ["H1"]
      relevant_figures: list[str]   # ["Fig2", "Fig3a"]
      paradigm: str                 # "delayed estimation task"
      stimuli: str                  # "oriented Gabor patches"
      procedure_summary: str        # "Brief description of trial sequence"
```

---

## Stage 3: FigureAnalysis

```yaml
figure_analysis:
  paper_id: str

  # Predictions (generated BEFORE looking at figures)
  predictions:
    - figure_id: str                # "Fig2a"
      from_hypothesis: str          # "H1"
      expected_chart_type: str      # "line plot or bar chart"
      expected_x_axis:
        label: str                  # "set size"
        values: list[str]           # ["2", "4", "6"]
      expected_y_axis:
        label: str                  # "recall error (degrees)"
        direction: str              # "lower is better"
      expected_groups:
        - label: str                # "uniform"
          expected_trend: str       # "increases with set size"
        - label: str                # "clustered"
          expected_trend: str       # "increases with set size, but less steeply"
      expected_pattern: str         # "clustered < uniform at set_size >= 4"
      expected_interaction: str     # "lines diverge as set_size increases"
      expected_statistics: str      # "significant interaction, p < .05"
      prediction_confidence: float  # 0.0-1.0 — how confident the system is in this prediction

  # Observations (from VLM analysis)
  observations:
    - figure_id: str                # "Fig2a"
      chart_type: str               # "line plot with error bars"
      x_axis:
        label: str                  # "set size"
        unit: str | null            # null for categorical
        range: str                  # "2, 4, 6"
        scale: str                  # "linear" | "log" | "categorical"
      y_axis:
        label: str                  # "mean recall error"
        unit: str                   # "degrees"
        range: str                  # "0-30"
        scale: str                  # "linear"
      elements:
        - label: str                # "uniform"
          color: str                # "blue"
          line_style: str | null    # "solid"
          marker: str | null        # "circle"
          estimated_values:         # Quantitative readings from plot
            - x: str                # "2"
              y: float              # 8.2
            - x: str                # "4"
              y: float              # 14.1
            - x: str                # "6"
              y: float              # 22.3
      error_bars:
        type: str                   # "SEM" | "SD" | "95% CI" | "unknown"
        present: bool
      significance_markers:
        - comparison: str           # "uniform vs clustered at set_size=6"
          marker: str               # "**"
          p_value: str | null       # "p < .01"
      inset_panels: list | null     # If figure has insets
      annotations: list[str]        # Any text annotations on the figure

  # Prediction-Observation Match
  matches:
    - figure_id: str                # "Fig2a"
      hypothesis_id: str            # "H1"
      match_result: enum            # "supported" | "partially_supported" | "not_supported" | "ambiguous"
      match_detail: str             # "Clustered < uniform at set_size 4,6 as predicted"
      surprises: list[str]          # ["Effect already present at set_size=4, stronger than expected"]
      concerns: list[str]           # ["Error bars overlap at set_size=4"]
      confidence: float             # 0.0-1.0
```

---

## Stage 4: DiscussionAnalysis

```yaml
discussion_analysis:
  paper_id: str

  # Author's Interpretation
  authors_interpretation: str       # "Results support efficient coding in VWM"
  interpretation_strength: enum     # "strong_claim" | "moderate_claim" | "tentative"

  # Alternative Explanations
  alternative_explanations:
    mentioned:
      - explanation: str            # "Attention-based account"
        how_addressed: str          # "Ruled out by Exp2 control condition"
    not_mentioned:                  # Critical gap — alternatives authors missed
      - explanation: str            # "Perceptual grouping confound"
        why_relevant: str           # "Clustered stimuli may be perceptually grouped"

  # Limitations
  limitations:
    acknowledged:
      - limitation: str             # "Small sample size (N=24)"
        severity: enum              # "minor" | "moderate" | "major"
    unacknowledged:
      - limitation: str             # "No control for stimulus salience differences"
        severity: enum
        why_matters: str

  # Broader Connections
  connections:
    - type: enum                    # "extends" | "contradicts" | "complements" | "replicates"
      target: str                   # "Taylor & Bays 2018"
      detail: str                   # "Extends their finding to naturalistic distributions"

  # Overall Assessment
  overall:
    strength_of_evidence: enum      # "strong" | "moderate" | "weak"
    novelty: enum                   # "high" | "moderate" | "incremental"
    methodological_rigor: enum      # "high" | "moderate" | "low"
    key_contribution: str           # One-sentence summary of what this paper adds
    open_questions: list[str]       # What remains unanswered
```

---

## Feedback Schema

```yaml
feedback_entry:
  id: str                          # UUID
  timestamp: datetime
  paper_id: str
  source: enum                     # "review_agent" | "user" | "automated_metric"

  # What was evaluated
  stage: enum                      # "stage1" | "stage2" | "stage3" | "stage4"
  component: str                   # "hypothesis_extraction" | "figure_axes" | etc.
  target_id: str | null            # "H1" | "Fig2a" | null

  # Evaluation
  score: int                       # 1-5
  feedback_type: enum              # "rating" | "correction" | "comment" | "rejection"
  detail:
    field: str | null              # Which specific field was wrong
    expected: str | null           # What it should have been
    actual: str | null             # What the system produced
    comment: str | null            # Free-form comment

  # Impact
  triggered_rerun: bool            # Did this feedback trigger a stage re-run?
  parameter_adjustments:           # What parameters were changed
    - parameter: str
      old_value: any
      new_value: any
```
