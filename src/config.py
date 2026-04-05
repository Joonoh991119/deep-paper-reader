"""Configuration management for the Deep Paper Reader pipeline.

Loads pipeline_config.yaml and model_registry.yaml,
provides typed access to all configuration values,
and supports runtime parameter adjustment from the feedback loop.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "configs"


class PipelineConfig:
    """Typed wrapper around pipeline_config.yaml."""

    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            config_path = _DEFAULT_CONFIG_DIR / "pipeline_config.yaml"
        self._path = Path(config_path)
        with open(self._path) as f:
            self._raw: dict[str, Any] = yaml.safe_load(f)
        self._adjustments: list[dict[str, Any]] = []

    # ── Stage 1 ─────────────────────────────────────────────────
    @property
    def parser(self) -> str:
        return self._raw["stage1"]["parser"]

    @property
    def skeleton_vlm(self) -> str:
        return self._raw["stage1"]["skeleton_vlm"]

    @property
    def figure_resolution(self) -> int:
        return self._raw["stage1"]["figure_resolution"]

    @property
    def chunk_size(self) -> int:
        return self._raw["stage1"]["chunk_size"]

    # ── Stage 2 ─────────────────────────────────────────────────
    @property
    def reasoning_model(self) -> str:
        return self._raw["stage2"]["reasoning_model"]

    @property
    def reasoning_temperature(self) -> float:
        return self._raw["stage2"]["reasoning_temperature"]

    @property
    def prompt_chain_depth(self) -> int:
        return self._raw["stage2"]["prompt_chain_depth"]

    @property
    def hypothesis_formality(self) -> str:
        return self._raw["stage2"]["hypothesis_formality"]

    # ── Stage 3 ─────────────────────────────────────────────────
    @property
    def figure_vlm(self) -> str:
        return self._raw["stage3"]["figure_vlm"]

    @property
    def figure_vlm_temperature(self) -> float:
        return self._raw["stage3"]["figure_vlm_temperature"]

    @property
    def prediction_specificity(self) -> str:
        return self._raw["stage3"]["prediction_specificity"]

    @property
    def num_quantitative_reads(self) -> int:
        return self._raw["stage3"]["num_quantitative_reads"]

    # ── Stage 4 ─────────────────────────────────────────────────
    @property
    def critical_depth(self) -> str:
        return self._raw["stage4"]["critical_depth"]

    # ── Embedding ───────────────────────────────────────────────
    @property
    def embedding_model(self) -> str:
        return self._raw["embedding"]["model"]

    @property
    def embedding_dimensions(self) -> int:
        return self._raw["embedding"]["dimensions"]

    @property
    def level_weights(self) -> dict[str, float]:
        return self._raw["embedding"]["level_weights"]

    # ── Feedback ────────────────────────────────────────────────
    @property
    def review_agent_enabled(self) -> bool:
        return self._raw["feedback"]["enable_review_agent"]

    @property
    def rerun_threshold(self) -> float:
        return self._raw["feedback"]["rerun_threshold"]

    # ── Parameter Adjustment ────────────────────────────────────

    def get(self, dotted_key: str) -> Any:
        """Get any config value by dotted path, e.g. 'stage3.figure_vlm_temperature'."""
        keys = dotted_key.split(".")
        node = self._raw
        for k in keys:
            node = node[k]
        return node

    def set(self, dotted_key: str, value: Any, reason: str = "") -> None:
        """Set a config value at runtime (feedback loop adjustment)."""
        keys = dotted_key.split(".")
        node = self._raw
        for k in keys[:-1]:
            node = node[k]
        old_value = node.get(keys[-1])
        node[keys[-1]] = value
        self._adjustments.append({
            "parameter": dotted_key,
            "old_value": old_value,
            "new_value": value,
            "reason": reason,
        })

    @property
    def adjustment_log(self) -> list[dict[str, Any]]:
        return list(self._adjustments)

    def save(self, path: str | Path | None = None) -> None:
        """Save current config (with adjustments) to disk."""
        out = path or self._path
        with open(out, "w") as f:
            yaml.dump(self._raw, f, default_flow_style=False, sort_keys=False)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._raw)


class ModelRegistry:
    """Lookup alternative models for any pipeline component."""

    def __init__(self, registry_path: str | Path | None = None):
        if registry_path is None:
            registry_path = _DEFAULT_CONFIG_DIR / "model_registry.yaml"
        with open(registry_path) as f:
            self._raw: dict[str, Any] = yaml.safe_load(f)
        self._models = self._raw.get("models", {})

    def get_primary(self, component: str) -> str:
        """Get the primary model for a component, e.g. 'figure_vlm'."""
        return self._models[component]["primary"]

    def get_alternatives(self, component: str) -> dict[str, Any]:
        """Get all alternatives for a component with full metadata."""
        return self._models[component]["alternatives"]

    def get_model_info(self, component: str, model_name: str) -> dict[str, Any]:
        """Get info for a specific model."""
        return self._models[component]["alternatives"][model_name]

    def list_components(self) -> list[str]:
        """List all pipeline components that have model alternatives."""
        return list(self._models.keys())

    def swap_primary(self, component: str, new_model: str) -> str:
        """Swap the primary model for a component. Returns old primary."""
        old = self._models[component]["primary"]
        if new_model not in self._models[component]["alternatives"]:
            raise ValueError(
                f"Model '{new_model}' not found in alternatives for '{component}'. "
                f"Available: {list(self._models[component]['alternatives'].keys())}"
            )
        self._models[component]["primary"] = new_model
        return old
