#!/usr/bin/env python3
"""SortSmart Ollama backend — runs vision models locally via Ollama.

Requires Ollama running: https://ollama.com
Default vision model: llava  (run: ollama pull llava)

Set in .env:
  OLLAMA_MODEL=llava          # or moondream, llava:13b, llama3.2-vision, etc.
  OLLAMA_HOST=http://localhost:11434   # optional, default
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

DEFAULT_OLLAMA_MODEL = "llava"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

IMAGE_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
STREAMS = {"wet", "dry", "sanitary", "special_care"}

# Map common LLaVA output variants → valid SortSmart stream names
_STREAM_MAP = {
    # dry / recyclable
    "dry": "dry", "recyclable": "dry", "recycling": "dry", "recycle": "dry",
    "paper": "dry", "plastic": "dry", "metal": "dry", "glass": "dry",
    "cardboard": "dry", "dry waste": "dry", "dry recyclable": "dry",
    "dry_waste": "dry", "dry recycling": "dry",
    # wet / organic / compost
    "wet": "wet", "organic": "wet", "compost": "wet", "compostable": "wet",
    "food": "wet", "food waste": "wet", "wet waste": "wet", "biodegradable": "wet",
    "kitchen waste": "wet", "wet_waste": "wet",
    # sanitary
    "sanitary": "sanitary", "hygiene": "sanitary", "bathroom": "sanitary",
    "medical": "sanitary", "sanitary waste": "sanitary", "sanitary_waste": "sanitary",
    # special_care / hazardous
    "special_care": "special_care", "special care": "special_care",
    "hazardous": "special_care", "e-waste": "special_care", "electronic": "special_care",
    "battery": "special_care", "chemical": "special_care", "toxic": "special_care",
    "ewaste": "special_care", "e_waste": "special_care", "special": "special_care",
    "special waste": "special_care", "special_care waste": "special_care",
    "electronics": "special_care",
}
RESULT_KEYS = {"item", "material", "stream", "prep_steps", "reason", "confidence", "contamination", "parts"}
PART_KEYS = {"item", "material", "stream", "prep_steps"}

SYSTEM_PROMPT = """You are SortSmart, a waste-sorting assistant for households in India.
Classify items using this prototype's four streams: wet, dry, sanitary, and
special_care. This is not a verified municipal rules database: do not claim
legal compliance or invent city-specific collection instructions. If local
rules may differ, say so in the reason and lower confidence.

Use the image or short description to identify the item, material, and visible
contamination. If it has separately sortable components (for example, a greasy
cardboard box and a clean plastic lid), give each component its own stream and
prep steps in parts. Otherwise include one part for the whole item. Keep the
overall stream as the main component's stream. Mention uncertain observations
as uncertain; do not infer hidden materials or contamination.

Return ONLY valid JSON with exactly these keys and types:
{"item":"","material":"","stream":"wet|dry|sanitary|special_care",
"contamination":"","parts":[{"item":"","material":"",
"stream":"wet|dry|sanitary|special_care","prep_steps":[]}],
"prep_steps":[],"reason":"","confidence":0.0}
The stream fields must be exactly wet, dry, sanitary, or special_care.
Translate text values to the requested language, but keep keys and stream
values in English. If unsure, lower confidence.
IMPORTANT: Return ONLY a single complete JSON object with ALL eight required
keys: item, material, stream, contamination, parts, prep_steps, reason,
confidence. Do NOT truncate or omit any key."""


def _normalize_stream(value):
    """Map LLaVA's natural language stream names to valid SortSmart values."""
    if not isinstance(value, str):
        return value
    key = value.strip().lower().replace("-", "_")
    return _STREAM_MAP.get(key, _STREAM_MAP.get(value.strip().lower(), value))


def _normalize_result(data):
    """Normalize stream fields in a result dict before validation."""
    if not isinstance(data, dict):
        return data
    if "stream" in data:
        data["stream"] = _normalize_stream(data["stream"])
    if "parts" in data and isinstance(data["parts"], list):
        for part in data["parts"]:
            if isinstance(part, dict) and "stream" in part:
                part["stream"] = _normalize_stream(part["stream"])
    return data


def validate_result(data):
    if not isinstance(data, dict) or set(data) != RESULT_KEYS:
        raise ValueError("The model response does not have the required JSON fields.")
    for field in ("item", "material", "reason", "contamination"):
        if not isinstance(data[field], str):
            raise ValueError(f"The {field} field must be a string.")
    _validate_stream(data["stream"])
    _validate_steps(data["prep_steps"])
    if not isinstance(data["parts"], list) or not 1 <= len(data["parts"]) <= 8:
        raise ValueError("The parts field must contain between 1 and 8 components.")
    for part in data["parts"]:
        if not isinstance(part, dict) or set(part) != PART_KEYS:
            raise ValueError("Each part must have item, material, stream, and prep_steps fields.")
        for field in ("item", "material"):
            if not isinstance(part[field], str):
                raise ValueError(f"Each part's {field} field must be a string.")
        _validate_stream(part["stream"])
        _validate_steps(part["prep_steps"])
    confidence = data["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError("The confidence field must be a number from 0 to 1.")
    return data


def _validate_stream(stream):
    if not isinstance(stream, str) or stream not in STREAMS:
        raise ValueError("The stream must be wet, dry, sanitary, or special_care.")


def _validate_steps(steps):
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        raise ValueError("Preparation steps must be a list of strings.")


def _ollama_is_running():
    """Check if Ollama server is reachable."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ollama_models():
    """Return list of locally available Ollama model names."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _pick_vision_model():
    """Pick the best available vision model, or return the configured default."""
    configured = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    available = _ollama_models()
    if not available:
        return configured  # offline or first run — will fail with a clear error
    # Prefer configured model if available
    if any(m.startswith(configured.split(":")[0]) for m in available):
        return configured
    # Fall back to any known vision model
    vision_models = ["llava", "moondream", "llama3.2-vision", "minicpm-v", "bakllava"]
    for vm in vision_models:
        if any(m.startswith(vm) for m in available):
            return next(m for m in available if m.startswith(vm))
    # Fall back to configured even if not found
    return configured


def _call_ollama(prompt, image_b64=None, model=None):
    """Call Ollama's /api/generate endpoint and return the response text."""
    model_id = model or _pick_vision_model()

    payload = {
        "model": model_id,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "system": SYSTEM_PROMPT,
        "options": {"temperature": 0, "num_predict": 1200},
    }
    if image_b64:
        payload["images"] = [image_b64]

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_HOST}. "
            "Make sure Ollama is running: open a Terminal and run  ollama serve"
        ) from exc


def _parse_response(text):
    """Parse and validate JSON from model response, stripping markdown fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # Find the first { ... } block
    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("The model did not return a JSON object.")
    try:
        result = json.loads(stripped[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError("The model returned invalid JSON.") from exc
    result = _normalize_result(result)
    return validate_result(result)


def analyze(image_bytes, media_type="image/jpeg", lang="English", model=None):
    """Analyze a waste item image using the local Ollama vision model."""
    if not image_bytes:
        raise ValueError("The selected image is empty.")
    if media_type not in IMAGE_TYPES.values():
        raise ValueError(f"Unsupported image media type: {media_type}")
    if not _ollama_is_running():
        raise RuntimeError(
            "Ollama is not running. Open Terminal and run:  ollama serve\n"
            "Then make sure a vision model is pulled:  ollama pull llava"
        )
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = f"Analyze the waste item in the image. Reply in {lang}."
    text = _call_ollama(prompt, image_b64=image_b64, model=model)
    return _parse_response(text)


def analyze_description(description, lang="English", model=None):
    """Analyze a text description using the local Ollama model."""
    description = description.strip()
    if not description:
        raise ValueError("Enter a short description of the item.")
    if len(description) > 300:
        raise ValueError("The item description must be 300 characters or fewer.")
    if not _ollama_is_running():
        raise RuntimeError(
            "Ollama is not running. Open Terminal and run:  ollama serve"
        )
    prompt = f"Analyze this waste item description: {description}\nReply in {lang}."
    text = _call_ollama(prompt, model=model)
    return _parse_response(text)


def active_provider_name():
    """Return display name of the active Ollama model."""
    model = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return f"Ollama local ({model})"


def ollama_status():
    """Return dict with Ollama health and available models."""
    running = _ollama_is_running()
    models = _ollama_models() if running else []
    vision_keywords = ["llava", "moondream", "vision", "minicpm", "bakllava"]
    vision = [m for m in models if any(kw in m.lower() for kw in vision_keywords)]
    return {
        "running": running,
        "models": models,
        "vision_models": vision,
        "active_model": _pick_vision_model() if running else None,
    }
