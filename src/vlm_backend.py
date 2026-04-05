"""VLM interface for figure description and deep interpretation.

Supports multiple VLM backends:
- Qwen3-VL (local via transformers)
- Gemini (via API)
- Claude (via API, vision)
- OpenAI-compatible (via API)

Each backend implements the same interface so they can be swapped
via model_registry.yaml.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VLMBackend(ABC):
    """Abstract base class for VLM backends."""

    @abstractmethod
    def describe_figure(self, image_path: str, caption: str) -> str:
        """Quick structural description of a figure (Stage 1)."""
        ...

    @abstractmethod
    def interpret_figure(
        self,
        image_path: str,
        caption: str,
        context_paragraph: str,
        structured_prompt: str,
    ) -> str:
        """Deep structured interpretation of a figure (Stage 3)."""
        ...


def _load_image_base64(image_path: str | Path) -> str:
    """Load an image file and return base64-encoded string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_media_type(image_path: str | Path) -> str:
    """Infer MIME type from file extension."""
    suffix = Path(image_path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".bmp": "image/bmp",
    }.get(suffix, "image/png")


# ─── Qwen3-VL Backend (Local) ──────────────────────────────────

class Qwen3VLBackend(VLMBackend):
    """Local Qwen3-VL inference via transformers."""

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3-VL-8B-Instruct",
        device: str = "auto",
        max_tokens: int = 2048,
    ):
        self.model_id = model_id
        self.device = device
        self.max_tokens = max_tokens
        self._model = None
        self._processor = None

    def _load_model(self) -> None:
        """Lazy-load the model on first use."""
        if self._model is not None:
            return
        try:
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
            import torch

            logger.info(f"Loading VLM: {self.model_id}")
            self._processor = AutoProcessor.from_pretrained(self.model_id)
            self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                self.model_id,
                torch_dtype=torch.bfloat16,
                device_map=self.device,
            )
            logger.info("VLM loaded successfully")
        except ImportError as e:
            raise RuntimeError(
                f"Qwen3-VL requires: pip install transformers torch qwen-vl-utils. Error: {e}"
            )

    def _run_inference(self, image_path: str, prompt: str, temperature: float = 0.1) -> str:
        """Run VLM inference on an image with a text prompt."""
        self._load_model()
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": f"file://{image_path}"},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos, video_kwargs = process_vision_info(messages, return_video_kwargs=True)
        inputs = self._processor(
            text=[text], images=images, videos=videos,
            padding=True, return_tensors="pt",
        ).to(self._model.device)

        output_ids = self._model.generate(
            **inputs,
            max_new_tokens=self.max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
        )
        # Trim input tokens from output
        trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
        return self._processor.batch_decode(trimmed, skip_special_tokens=True)[0]

    def describe_figure(self, image_path: str, caption: str) -> str:
        prompt = (
            "You are a scientific figure analyst. Provide a brief structural description.\n"
            "Focus on: chart type, axes, number of conditions, error bars, "
            "statistical annotations, notable patterns.\n"
            "Keep under 100 words. Be factual.\n\n"
            f"Caption: {caption}"
        )
        return self._run_inference(image_path, prompt)

    def interpret_figure(
        self,
        image_path: str,
        caption: str,
        context_paragraph: str,
        structured_prompt: str,
    ) -> str:
        full_prompt = structured_prompt.format(
            caption=caption,
            context_paragraph=context_paragraph,
        )
        return self._run_inference(image_path, full_prompt, temperature=0.1)


# ─── Anthropic Claude Backend (API) ─────────────────────────────

class ClaudeVisionBackend(VLMBackend):
    """Claude API with vision capabilities."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", max_tokens: int = 2048):
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def _run_inference(self, image_path: str, prompt: str) -> str:
        client = self._get_client()
        img_data = _load_image_base64(image_path)
        media_type = _get_media_type(image_path)

        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": img_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return response.content[0].text

    def describe_figure(self, image_path: str, caption: str) -> str:
        prompt = (
            "You are a scientific figure analyst. Provide a brief structural description.\n"
            "Focus on: chart type, axes, number of conditions, error bars, "
            "statistical annotations, notable patterns.\n"
            "Keep under 100 words. Be factual.\n\n"
            f"Caption: {caption}"
        )
        return self._run_inference(image_path, prompt)

    def interpret_figure(
        self,
        image_path: str,
        caption: str,
        context_paragraph: str,
        structured_prompt: str,
    ) -> str:
        full_prompt = structured_prompt.format(
            caption=caption,
            context_paragraph=context_paragraph,
        )
        return self._run_inference(image_path, full_prompt)


# ─── Gemini Backend (API) ───────────────────────────────────────

class GeminiVisionBackend(VLMBackend):
    """Google Gemini API with vision."""

    def __init__(self, model: str = "gemini-2.5-flash", max_tokens: int = 2048):
        self.model = model
        self.max_tokens = max_tokens

    def _run_inference(self, image_path: str, prompt: str) -> str:
        try:
            import google.genai as genai

            client = genai.Client()
            img_data = _load_image_base64(image_path)
            media_type = _get_media_type(image_path)

            response = client.models.generate_content(
                model=self.model,
                contents=[
                    {
                        "parts": [
                            {"inline_data": {"mime_type": media_type, "data": img_data}},
                            {"text": prompt},
                        ]
                    }
                ],
            )
            return response.text
        except ImportError:
            raise RuntimeError("Gemini requires: pip install google-genai")

    def describe_figure(self, image_path: str, caption: str) -> str:
        prompt = (
            "You are a scientific figure analyst. Provide a brief structural description.\n"
            f"Caption: {caption}\n"
            "Focus on chart type, axes, conditions, error bars, stats. Under 100 words."
        )
        return self._run_inference(image_path, prompt)

    def interpret_figure(
        self,
        image_path: str,
        caption: str,
        context_paragraph: str,
        structured_prompt: str,
    ) -> str:
        full_prompt = structured_prompt.format(
            caption=caption,
            context_paragraph=context_paragraph,
        )
        return self._run_inference(image_path, full_prompt)


# ─── Factory ────────────────────────────────────────────────────

_BACKENDS: dict[str, type[VLMBackend]] = {
    "qwen3-vl-8b": Qwen3VLBackend,
    "qwen3-vl-72b": Qwen3VLBackend,
    "qwen2.5-vl-72b": Qwen3VLBackend,
    "internvl3-8b": Qwen3VLBackend,  # Similar HF interface
    "claude-sonnet-4": ClaudeVisionBackend,
    "gemini-2.5-pro": GeminiVisionBackend,
    "gemini-2.5-flash": GeminiVisionBackend,
}

_MODEL_IDS: dict[str, str] = {
    "qwen3-vl-8b": "Qwen/Qwen3-VL-8B-Instruct",
    "qwen3-vl-72b": "Qwen/Qwen3-VL-72B-Instruct",
    "qwen2.5-vl-72b": "Qwen/Qwen2.5-VL-72B-Instruct",
    "internvl3-8b": "OpenGVLab/InternVL3-8B",
    "claude-sonnet-4": "claude-sonnet-4-20250514",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
}


def create_vlm_backend(model_name: str, **kwargs) -> VLMBackend:
    """Factory function to create a VLM backend by model name."""
    backend_cls = _BACKENDS.get(model_name)
    if backend_cls is None:
        raise ValueError(
            f"Unknown VLM: {model_name}. Available: {list(_BACKENDS.keys())}"
        )

    model_id = _MODEL_IDS.get(model_name, model_name)

    if backend_cls == Qwen3VLBackend:
        return backend_cls(model_id=model_id, **kwargs)
    elif backend_cls == ClaudeVisionBackend:
        return backend_cls(model=model_id, **kwargs)
    elif backend_cls == GeminiVisionBackend:
        return backend_cls(model=model_id, **kwargs)
    else:
        return backend_cls(**kwargs)
