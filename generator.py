"""Deterministic requirement analysis and test artifact generation."""
from __future__ import annotations

import json
import re
from typing import Any

VAGUE_TERMS = re.compile(r"\b(correct(?:ly)?|quick(?:ly)?|fast|appropriate(?:ly)?|easy|easily|seamless(?:ly)?|secure(?:ly)?|proper(?:ly)?|as expected|user[- ]friendly|intuitive|efficient(?:ly)?)\b", re.I)
VALIDATION_TERMS = re.compile(r"\b(required|empty|blank|missing|invalid|validation|validate)\b", re.I)
ERROR_TERMS = re.compile(r"\b(error|message|inline|block|prevent|cannot|can't|must not|disabled|highlight)\b", re.I)
HIGH_RISK = re.compile(r"\b(payment|checkout|purchase|order|personal data|address|delete|permission|authorization|password|security|refund)\b", re.I)
MEDIUM_RISK = re.compile(r"\b(login|sign in|cart|price|tax|total|account|session|search|sort|filter)\b", re.I)


def parse_criteria(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        entries: list[Any] = value.splitlines()
    elif isinstance(value, list):
        entries = value
    else:
        raise ValueError("Acceptance criteria must be a list or newline-separated text.")
    criteria: list[dict[str, str]] = []
    for entry in entries:
        if isinstance(entry, dict):
            raw_id = str(entry.get("id", "")).strip()
            match = re.fullmatch(r"AC[-_ ]?(\d+)", raw_id, re.I)
            if not match:
                raise ValueError("Structured acceptance criteria need an ID such as AC-01.")
            cid = "AC-" + match.group(1).zfill(2)
            body = str(entry.get("text", "")).strip()
            if not body:
                raise ValueError(f"{cid} has no acceptance-criterion text.")
            criteria.append({"id": cid, "text": body})
            continue

        line = str(entry)
        text = line.strip().lstrip("-•* ").strip()
        if not text:
            continue
        match = re.match(r"^(AC[-_ ]?\d+)\s*[:|.)-]?\s*(.*)$", text, re.I)
        if match:
            cid, body = match.group(1).upper().replace("_", "-").replace(" ", "-"), match.group(2).strip()
            if not cid.startswith("AC-"):
                cid = "AC-" + re.sub(r"\D", "", cid)
        else:
            cid, body = f"AC-{len(criteria) + 1:02d}", text
        if not body:
            raise ValueError(f"{cid} has no acceptance-criterion text.")
        criteria.append({"id": cid, "text": body})
    if not criteria:
        raise ValueError("Add at least one acceptance criterion.")
    if len(criteria) > 12:
        raise ValueError("Use 12 or fewer acceptance criteria per run.")
    ids = [item["id"] for item in criteria]
    if len(ids) != len(set(ids)):
        raise ValueError("Acceptance criterion IDs must be unique.")
    return criteria


def analyze_ambiguity(criteria: list[dict[str, str]]) -> list[dict[str, str]]:
    flags = []
    for item in criteria:
        text = item["text"]
        reasons = []
        if VAGUE_TERMS.search(text):
            reasons.append("Uses subjective wording without a measurable threshold or example.")
        if VALIDATION_TERMS.search(text) and not ERROR_TERMS.search(text):
            reasons.append("Describes validation but does not say what the user sees or what action is blocked.")
        if re.search(r"\b(tax|total|subtotal)\b", text, re.I) and not re.search(r"\b(rate|formula|round|decimal|currency|sum|equals|equal to|calculated)\b", text, re.I):
            reasons.append("Mentions a monetary amount but leaves its calculation or rounding rule unspecified.")
        if reasons:
            flags.append({"criterionId": item["id"], "text": text, "severity": "Needs clarification", "reasons": reasons,
                          "question": _clarification_question(text, reasons)})
    return flags


def _clarification_question(text: str, reasons: list[str]) -> str:
    low = text.lower()
    if re.search(r"\b(tax|total|subtotal)\b", low):
        return "Which formula, currency, and rounding rule should be used?"
    if VALIDATION_TERMS.search(text):
        return "What exact message or visual state should appear, and should submission be blocked?"
    if VAGUE_TERMS.search(text):
        return "What observable threshold or example defines this outcome?"
    return "What observable result should a tester assert?"


def risk_for(text: str) -> dict[str, Any]:
    if HIGH_RISK.search(text):
        level, score, probability = "High", 3, 2
    elif MEDIUM_RISK.search(text):
        level, score, probability = "Medium", 2, 2
    else:
        level, score, probability = "Low", 1, 1
    return {"level": level, "impact": score, "likelihood": probability, "score": score * probability,
            "rationale": {"High": "A failure could affect an order, sensitive data, access, or a consequential action.",
                          "Medium": "A failure could disrupt a common user journey or display business-critical information.",
                          "Low": "A failure is likely to have a limited effect on the core user journey."}[level]}


def _scenario_for(item: dict[str, str], feature: str) -> dict[str, Any]:
    text = item["text"]
    kind = "negative" if VALIDATION_TERMS.search(text) or re.search(r"\b(cannot|can't|must not|deny|reject|empty|invalid)\b", text, re.I) else "positive"
    risk = risk_for(text)
    slug = re.sub(r"[^a-z0-9]+", "-", item["id"].lower()).strip("-")
    return {
        "id": "TS-" + slug.removeprefix("ac-"), "title": f"{item['id']}: {_sentence(text)}", "acceptanceIds": [item["id"]],
        "kind": kind, "risk": risk, "preconditions": [f"The tester can access the {feature or 'target'} flow."],
        "steps": ["Open the relevant page or flow.", f"Exercise the behavior described by {item['id']} using representative synthetic data."],
        "expectedResult": f"The application satisfies this acceptance criterion: {text}", "rationale": risk["rationale"], "source": "baseline"
    }


def _sentence(text: str) -> str:
    result = text.strip().rstrip(".?!")
    return result[:180]


def _gherkin(product: str, feature: str, scenarios: list[dict[str, Any]]) -> str:
    name = feature or "The requested user journey"
    lines = [f"Feature: {name}", f"  As a user of {product or 'the application'}", "  I want the behavior in the acceptance criteria", "  So that the journey is predictable", ""]
    for scenario in scenarios:
        tags = " ".join([*("@" + cid.lower() for cid in scenario["acceptanceIds"]), "@" + scenario["id"].lower(), "@risk-" + scenario["risk"]["level"].lower()])
        lines += [f"  {tags}", f"  Scenario: {scenario['title']}"]
        for step in scenario.get("steps", []):
            lines.append("    Given " + step if "access" in step.lower() else "    When " + step)
        lines.append("    Then " + scenario["expectedResult"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _cypress(product: str, url: str, feature: str, scenarios: list[dict[str, Any]]) -> str:
    title = feature or "generated acceptance scenarios"
    site = url or "https://example.test"
    lines = ["// Draft generated from synthetic requirements. Add reviewed setup and selectors before running.", "// Every test starts skipped; unskip only after review. This does not crawl the target website.", f"const baseUrl = Cypress.env('BASE_URL') || {json.dumps(site, ensure_ascii=False)};", "", f"describe({json.dumps(title, ensure_ascii=False)}, () => {{", "  beforeEach(() => {", "    cy.visit(baseUrl);", "  });", ""]
    for scenario in scenarios:
        lines += [f"  it.skip({json.dumps(scenario['id'] + ': ' + scenario['title'], ensure_ascii=False)}, () => {{",
                  f"    // Traceability: {', '.join(scenario['acceptanceIds'])} | Risk: {scenario['risk']['level']}"]
        code = _saucedemo_example(scenario, product)
        if code:
            lines.extend("    " + line if line else "" for line in code.splitlines())
        else:
            lines += ["    // TODO: arrange synthetic data and perform the user action.", "    // TODO: assert the observable result from the acceptance criterion."]
        lines += ["  });", ""]
    lines.append("});")
    return "\n".join(lines) + "\n"


def _saucedemo_example(scenario: dict[str, Any], product: str) -> str:
    text = " ".join([scenario["title"], scenario["expectedResult"]]).lower()
    if "sauce" not in product.lower() and "saucedemo" not in product.lower():
        return ""
    if "cart" in text and ("visible" in text or "selected" in text or "item" in text):
        return "\n".join([
            "// Review the product choice and selector against the current demo UI.",
            "cy.get('[data-test=\"add-to-cart-sauce-labs-backpack\"]').click();",
            "cy.get('[data-test=\"shopping-cart-link\"]').click();",
            "cy.get('[data-test=\"inventory-item-name\"]').should('contain.text', 'Sauce Labs Backpack');"])
    if "subtotal" in text or "tax" in text or "total" in text:
        return "\n".join([
            "// Review the arithmetic and currency/rounding expectations with the product owner.",
            "cy.get('[data-test=\"item-total\"]').should('be.visible');",
            "cy.get('[data-test=\"tax-label\"]').should('be.visible');",
            "cy.get('[data-test=\"total-label\"]').should('be.visible');"])
    if "confirm" in text or "complete" in text or "finish" in text:
        return "\n".join([
            "// This journey assumes a logged-in user with a prepared cart; add setup before running.",
            "cy.get('[data-test=\"finish\"]').click();",
            "cy.get('[data-test=\"complete-header\"]').should('be.visible');"])
    if "required" in text or "validation" in text or "empty" in text:
        return "\n".join([
            "// Confirm exact error wording and whether the first empty field is reported at a time.",
            "cy.get('[data-test=\"continue\"]').click();",
            "cy.get('[data-test=\"error\"]').should('be.visible');"])
    return ""


def build_artifacts(payload: dict[str, Any], ai_scenarios: list[dict[str, Any]] | None = None, engine: str = "Local rules") -> dict[str, Any]:
    criteria = parse_criteria(payload.get("criteria", []))
    product = str(payload.get("product", "")).strip()[:120]
    feature = str(payload.get("feature", "")).strip()[:120]
    url = str(payload.get("url", "")).strip()[:300]
    story = str(payload.get("story", "")).strip()[:2000]
    baseline = [_scenario_for(item, feature) for item in criteria]
    allowed = {item["id"] for item in criteria}
    extras: list[dict[str, Any]] = []
    for raw in (ai_scenarios or [])[:8]:
        if not isinstance(raw, dict):
            continue
        raw_ids = raw.get("acceptanceIds", [])
        if not isinstance(raw_ids, list):
            continue
        mapped = [cid for cid in raw_ids if isinstance(cid, str) and cid in allowed]
        if not mapped:
            continue
        risk = risk_for(" ".join([str(raw.get("title", "")), *[next(c["text"] for c in criteria if c["id"] == cid) for cid in mapped]]))
        raw_preconditions = raw.get("preconditions", [])
        raw_steps = raw.get("steps", [])
        if not isinstance(raw_preconditions, list):
            raw_preconditions = []
        if not isinstance(raw_steps, list):
            raw_steps = []
        extras.append({"id": f"AI-{len(extras) + 1:02d}", "title": _sentence(str(raw.get("title", "Exploratory scenario"))),
                       "acceptanceIds": mapped, "kind": raw.get("kind") if raw.get("kind") in {"positive", "negative", "boundary", "security", "accessibility"} else "exploratory",
                       "risk": risk, "preconditions": [str(x)[:180] for x in raw_preconditions[:4]],
                       "steps": [str(x)[:240] for x in raw_steps[:8]],
                       "expectedResult": str(raw.get("expectedResult", "Review the observable result with the product owner."))[:400],
                       "rationale": str(raw.get("rationale", "AI-suggested addition; review before use."))[:240], "source": "ai"})
    scenarios = baseline + extras
    ambiguities = analyze_ambiguity(criteria)
    traceability = []
    for item in criteria:
        ids = [s["id"] for s in scenarios if item["id"] in s["acceptanceIds"]]
        traceability.append({"criterionId": item["id"], "criterion": item["text"], "scenarioIds": ids, "covered": bool(ids)})
    return {"product": product or "Unspecified demo", "url": url, "feature": feature or "User journey", "story": story,
            "engine": engine, "criteria": criteria, "scenarios": scenarios, "ambiguities": ambiguities, "traceability": traceability,
            "coverage": round(sum(row["covered"] for row in traceability) / len(traceability) * 100) if traceability else 0,
            "riskSummary": {level: sum(s["risk"]["level"] == level for s in scenarios) for level in ["High", "Medium", "Low"]},
            "gherkin": _gherkin(product, feature, scenarios), "cypress": _cypress(product, url, feature, baseline)}
