"""Optional server-side OpenAI Responses API integration. No request data is persisted."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class AIProviderError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def generate_additional_scenarios(
    payload: dict[str, Any],
    criteria: list[dict[str, str]],
    project_memory: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return []
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    input_data = {
        "product": payload.get("product"),
        "feature": payload.get("feature"),
        "story": payload.get("story"),
        "criteria": criteria,
        "approved_examples_from_this_project": (project_memory or [])[:8],
    }
    prompt = (
        "You are a careful QA analyst. Suggest up to 4 additional edge, negative, boundary, accessibility, or security scenarios "
        "that add value beyond one baseline test per acceptance criterion. Use only synthetic data. Never invent product behavior as fact. "
        "Each scenario must map to one or more supplied criterion IDs. Keep the output concise and return JSON only with this shape: "
        '{"additionalScenarios":[{"title":"...","acceptanceIds":["AC-01"],"kind":"boundary","preconditions":["..."],"steps":["..."],"expectedResult":"...","rationale":"..."}]}. '
        "Approved examples from this project may guide style and useful coverage, but they are not proof of current product behavior. "
        "Do not copy an old example unless it fits the current criteria. Do not include a scenario if its expected result cannot be grounded "
        "in the current supplied criteria; instead formulate a question in rationale."
    )
    body = json.dumps({"model": model, "store": False, "max_output_tokens": 1800,
                       "input": [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}]}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIProviderError("The AI request did not complete. Check the key, network connection, and model setting.") from exc
    texts = []
    for output in result.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                texts.append(content.get("text", ""))
    raw_text = "\n".join(texts).strip()
    try:
        decoded = json.loads(raw_text)
        scenarios = decoded.get("additionalScenarios", [])
        if not isinstance(scenarios, list):
            raise ValueError("Expected a list of scenarios.")
        return scenarios[:4]
    except (json.JSONDecodeError, ValueError, AttributeError) as exc:
        raise AIProviderError("The AI response did not match the expected JSON shape.") from exc
