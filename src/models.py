"""Core data models for the Deep Paper Reader pipeline.

All structured outputs are defined here as Pydantic models,
ensuring type safety and serialization to YAML/JSON.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────────

class PaperType(str, Enum):
    EMPIRICAL = "empirical"
    COMPUTATIONAL = "computational"
    REVIEW = "review"
    METHODS = "methods"
    CASE_STUDY = "case_study"


class SectionType(str, Enum):
    INTRODUCTION = "introduction"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    SUPPLEMENTARY = "supplementary"
    REFERENCES = "references"
    APPENDIX = "appendix"
    OTHER = "other"


class GapType(str, Enum):
    UNEXPLORED = "unexplored"
    CONTRADICTORY = "contradictory_findings"
    METHODOLOGICAL = "methodological_limitation"
    THEORETICAL = "theoretical_gap"


class ClaimType(str, Enum):
    NOVEL_MECHANISM = "novel_mechanism"
    EXTENDS_EXISTING = "extends_existing"
    CONTRADICTS_EXISTING = "contradicts_existing"
    UNIFYING_FRAMEWORK = "unifying_framework"


class FactorType(str, Enum):
    WITHIN = "within"
    BETWEEN = "between"
    MIXED = "mixed"


class MatchResult(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_SUPPORTED = "not_supported"
    AMBIGUOUS = "ambiguous"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class Novelty(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    INCREMENTAL = "incremental"


class Severity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"


class ConnectionType(str, Enum):
    EXTENDS = "extends"
    CONTRADICTS = "contradicts"
    COMPLEMENTS = "complements"
    REPLICATES = "replicates"


class FeedbackSource(str, Enum):
    REVIEW_AGENT = "review_agent"
    USER = "user"
    AUTOMATED_METRIC = "automated_metric"


class FeedbackType(str, Enum):
    RATING = "rating"
    CORRECTION = "correction"
    COMMENT = "comment"
    REJECTION = "rejection"
    APPROVAL = "approval"


# ─── Stage 1: Skeleton ─────────────────────────────────────────

class Author(BaseModel):
    name: str
    affiliation: str = ""


class SectionInfo(BaseModel):
    id: str
    title: str
    start_page: int = 0
    type: SectionType = SectionType.OTHER


class SubFigure(BaseModel):
    id: str
    image_path: str = ""
    caption_segment: str = ""


class FigureInfo(BaseModel):
    id: str
    image_path: str = ""
    caption: str = ""
    section_context: str = ""
    vlm_initial_description: str = ""
    has_subfigures: bool = False
    subfigures: list[SubFigure] = Field(default_factory=list)


class TableInfo(BaseModel):
    id: str
    content_html: str = ""
    caption: str = ""
    section_context: str = ""


class EquationInfo(BaseModel):
    id: str
    latex: str = ""
    context: str = ""


class PaperSkeleton(BaseModel):
    """Stage 1 output: structural overview of the paper."""
    doi: str = ""
    title: str = ""
    authors: list[Author] = Field(default_factory=list)
    journal: str = ""
    year: int = 0
    paper_type: PaperType = PaperType.EMPIRICAL

    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)

    graphical_abstract_present: bool = False
    graphical_abstract_description: str = ""

    sections: list[SectionInfo] = Field(default_factory=list)
    figures: list[FigureInfo] = Field(default_factory=list)
    tables: list[TableInfo] = Field(default_factory=list)
    equations: list[EquationInfo] = Field(default_factory=list)

    num_experiments_estimated: int = 0
    total_pages: int = 0

    # Raw text by section (for downstream stages)
    section_texts: dict[str, str] = Field(default_factory=dict)


# ─── Stage 2: Argument Structure ───────────────────────────────

class BackgroundClaim(BaseModel):
    claim: str
    citations: list[str] = Field(default_factory=list)
    is_consensus: bool = True
    domain: str = ""


class ResearchGap(BaseModel):
    statement: str
    type: GapType = GapType.UNEXPLORED
    prior_attempts: list[str] = Field(default_factory=list)


class MainClaim(BaseModel):
    statement: str
    claim_type: ClaimType = ClaimType.NOVEL_MECHANISM
    theoretical_framework: str = ""


class VariableSpec(BaseModel):
    name: str
    levels: list[str] = Field(default_factory=list)
    type: FactorType = FactorType.WITHIN


class DVSpec(BaseModel):
    name: str
    unit: str = ""
    measurement: str = ""


class Operationalization(BaseModel):
    independent_variable: VariableSpec
    dependent_variable: DVSpec
    controls: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    id: str
    verbal: str
    formal: str = ""
    predicted_direction: str = ""
    is_directional: bool = True
    relevant_figures: list[str] = Field(default_factory=list)
    key_metric: str = ""
    operationalization: Optional[Operationalization] = None
    alternative_if_false: str = ""


class ExperimentalFactor(BaseModel):
    name: str
    levels: list[str] = Field(default_factory=list)
    type: FactorType = FactorType.WITHIN


class Experiment(BaseModel):
    id: str
    design: str = ""
    factors: list[ExperimentalFactor] = Field(default_factory=list)
    n_participants: int = 0
    measure: str = ""
    statistical_tests: list[str] = Field(default_factory=list)
    maps_to_hypotheses: list[str] = Field(default_factory=list)
    relevant_figures: list[str] = Field(default_factory=list)
    paradigm: str = ""
    stimuli: str = ""
    procedure_summary: str = ""


class ArgumentStructure(BaseModel):
    """Stage 2 output: logical argument of the paper."""
    paper_id: str = ""
    background_claims: list[BackgroundClaim] = Field(default_factory=list)
    research_gap: Optional[ResearchGap] = None
    main_claim: Optional[MainClaim] = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)


# ─── Stage 3: Figure Analysis ──────────────────────────────────

class AxisSpec(BaseModel):
    label: str = ""
    values: list[str] = Field(default_factory=list)


class AxisObservation(BaseModel):
    label: str = ""
    unit: str = ""
    range: str = ""
    scale: str = "linear"  # linear, log, categorical


class DataPoint(BaseModel):
    x: str
    y: float


class GroupPrediction(BaseModel):
    label: str
    expected_trend: str = ""


class FigurePrediction(BaseModel):
    figure_id: str
    from_hypothesis: str
    expected_chart_type: str = ""
    expected_x_axis: Optional[AxisSpec] = None
    expected_y_axis: Optional[AxisSpec] = None
    expected_groups: list[GroupPrediction] = Field(default_factory=list)
    expected_pattern: str = ""
    expected_interaction: str = ""
    expected_statistics: str = ""
    prediction_confidence: float = 0.5


class DataElement(BaseModel):
    label: str = ""
    color: str = ""
    line_style: str = ""
    marker: str = ""
    estimated_values: list[DataPoint] = Field(default_factory=list)


class ErrorBarInfo(BaseModel):
    type: str = "unknown"  # SEM, SD, 95%CI, unknown
    present: bool = False


class SignificanceMarker(BaseModel):
    comparison: str = ""
    marker: str = ""
    p_value: str = ""


class FigureObservation(BaseModel):
    figure_id: str
    chart_type: str = ""
    x_axis: Optional[AxisObservation] = None
    y_axis: Optional[AxisObservation] = None
    elements: list[DataElement] = Field(default_factory=list)
    error_bars: ErrorBarInfo = Field(default_factory=ErrorBarInfo)
    significance_markers: list[SignificanceMarker] = Field(default_factory=list)
    main_trends: list[str] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)


class PredictionMatch(BaseModel):
    figure_id: str
    hypothesis_id: str
    match_result: MatchResult = MatchResult.AMBIGUOUS
    match_detail: str = ""
    surprises: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class FigureAnalysis(BaseModel):
    """Stage 3 output: figure interpretation and prediction matching."""
    paper_id: str = ""
    predictions: list[FigurePrediction] = Field(default_factory=list)
    observations: list[FigureObservation] = Field(default_factory=list)
    matches: list[PredictionMatch] = Field(default_factory=list)


# ─── Stage 4: Discussion ───────────────────────────────────────

class AlternativeExplanation(BaseModel):
    explanation: str
    how_addressed: str = ""


class UnmentionedAlternative(BaseModel):
    explanation: str
    why_relevant: str = ""


class Limitation(BaseModel):
    limitation: str
    severity: Severity = Severity.MODERATE


class UnacknowledgedLimitation(BaseModel):
    limitation: str
    severity: Severity = Severity.MODERATE
    why_matters: str = ""


class FieldConnection(BaseModel):
    type: ConnectionType
    target: str
    detail: str = ""


class DiscussionAnalysis(BaseModel):
    """Stage 4 output: critical discussion analysis."""
    paper_id: str = ""
    authors_interpretation: str = ""
    interpretation_strength: str = "moderate_claim"

    alternatives_mentioned: list[AlternativeExplanation] = Field(default_factory=list)
    alternatives_not_mentioned: list[UnmentionedAlternative] = Field(default_factory=list)

    limitations_acknowledged: list[Limitation] = Field(default_factory=list)
    limitations_unacknowledged: list[UnacknowledgedLimitation] = Field(default_factory=list)

    connections: list[FieldConnection] = Field(default_factory=list)

    strength_of_evidence: EvidenceStrength = EvidenceStrength.MODERATE
    novelty: Novelty = Novelty.MODERATE
    methodological_rigor: str = "moderate"
    key_contribution: str = ""
    open_questions: list[str] = Field(default_factory=list)


# ─── Feedback ───────────────────────────────────────────────────

class ParameterAdjustment(BaseModel):
    parameter: str
    old_value: str = ""
    new_value: str = ""


class FeedbackDetail(BaseModel):
    field: str = ""
    expected: str = ""
    actual: str = ""
    comment: str = ""


class FeedbackEntry(BaseModel):
    id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    paper_id: str = ""
    source: FeedbackSource = FeedbackSource.REVIEW_AGENT

    stage: str = ""
    component: str = ""
    target_id: str = ""

    score: int = 3
    feedback_type: FeedbackType = FeedbackType.RATING
    detail: Optional[FeedbackDetail] = None

    triggered_rerun: bool = False
    parameter_adjustments: list[ParameterAdjustment] = Field(default_factory=list)


class ReviewScore(BaseModel):
    dimension: str
    score: int
    justification: str = ""
    correction: str = ""


class StageReview(BaseModel):
    stage: str
    paper_id: str
    scores: list[ReviewScore] = Field(default_factory=list)
    overall_score: float = 0.0
    critical_issues: list[str] = Field(default_factory=list)
    suggested_parameter_changes: list[ParameterAdjustment] = Field(default_factory=list)


# ─── Full Pipeline Output ──────────────────────────────────────

class PaperReadingResult(BaseModel):
    """Complete output from processing one paper through all stages."""
    skeleton: PaperSkeleton
    argument: ArgumentStructure
    figures: FigureAnalysis
    discussion: DiscussionAnalysis
    review: Optional[StageReview] = None
    feedback: list[FeedbackEntry] = Field(default_factory=list)
    processing_time_seconds: float = 0.0
    pipeline_version: str = "0.1.0"
