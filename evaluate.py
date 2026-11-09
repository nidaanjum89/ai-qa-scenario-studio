"""Run the small, reproducible generator evaluation set."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from generator import analyze_ambiguity, build_artifacts

DATA = Path(__file__).resolve().parent / "data" / "evaluation_cases.json"


def run_evaluation() -> dict[str, Any]:
    cases = json.loads(DATA.read_text(encoding="utf-8"))
    covered = total = expected_flags = detected_flags = 0
    details = []
    for case in cases:
        result = build_artifacts(case["input"])
        total += len(result["traceability"])
        covered += sum(row["covered"] for row in result["traceability"])
        expected = set(case.get("expectedAmbiguousIds", []))
        detected = {flag["criterionId"] for flag in result["ambiguities"]}
        expected_flags += len(expected)
        detected_flags += len(expected & detected)
        details.append({"name": case["name"], "coverage": result["coverage"], "expectedAmbiguityIds": sorted(expected), "detectedAmbiguityIds": sorted(detected), "pass": result["coverage"] == 100 and expected <= detected})
    return {"caseCount": len(cases), "criterionCoverage": round(covered / total * 100) if total else 100,
            "ambiguityRecall": round(detected_flags / expected_flags * 100) if expected_flags else 100,
            "details": details, "scopeNote": "Checks deterministic rules against synthetic fixtures; not a measure of real-world QA quality or LLM accuracy."}


def main() -> None:
    result = run_evaluation()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["criterionCoverage"] < 100 or any(not item["pass"] for item in result["details"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
