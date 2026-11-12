"""Deterministic requirement analysis and test artifact generation."""
from __future__ import annotations

import json
import re
from typing import Any

VAGUE_TERMS = re.compile(r"\b(correct(?:ly)?|clear(?:ly)?|quick(?:ly)?|fast|appropriate(?:ly)?|easy|easily|seamless(?:ly)?|secure(?:ly)?|proper(?:ly)?|as expected|user[- ]friendly|intuitive|efficient(?:ly)?)\b", re.I)
VALIDATION_TERMS = re.compile(r"\b(required|empty|blank|missing|invalid|validation|validate)\b", re.I)
ERROR_TERMS = re.compile(r"\b(error|message|inline|block|prevent|cannot|can't|must not|disabled|highlight)\b", re.I)
HIGH_RISK = re.compile(r"\b(payment|checkout|purchase|order|personal data|address|delete|permission|authorization|password|security|refund)\b", re.I)
MEDIUM_RISK = re.compile(r"\b(login|sign in|cart|price|tax|total|account|session|search|sort|filter)\b", re.I)
PHOTO_TERMS = re.compile(r"\b(photo|picture|image|upload|photograph)\b", re.I)
WARDROBE_TERMS = re.compile(r"\b(wardrobe|clothing|apparel|garment|shirt|pant|scarf|trouser|jeans)\b", re.I)
CLOTHING_EXAMPLES = re.compile(r"\b(shirts?|pants?|scarves?|trousers?|jeans)\b", re.I)
CLASSIFICATION_TERMS = re.compile(r"\b(classif(?:y|ies|ication)|categor(?:y|ize|ies|ized)|detect|recogniz|auto[- ]?fill|autofill|color|style)\b", re.I)
SAVE_TERMS = re.compile(r"\b(save|saved|store|persist)\b", re.I)


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


def analyze_ambiguity(criteria: list[dict[str, str]], story: str = "", feature: str = "") -> list[dict[str, str]]:
    flags = []
    context = " ".join([story, feature, *(item["text"] for item in criteria)])
    photo_classification = bool(PHOTO_TERMS.search(context) and (CLASSIFICATION_TERMS.search(context) or WARDROBE_TERMS.search(context)))
    for item in criteria:
        text = item["text"]
        reasons = []
        if VAGUE_TERMS.search(text):
            reasons.append("Uses subjective wording without a measurable threshold or example.")
        if VALIDATION_TERMS.search(text) and not ERROR_TERMS.search(text):
            reasons.append("Describes validation but does not say what the user sees or what action is blocked.")
        if re.search(r"\b(tax|total|subtotal)\b", text, re.I) and not re.search(r"\b(rate|formula|round|decimal|currency|sum|equals|equal to|calculated)\b", text, re.I):
            reasons.append("Mentions a monetary amount but leaves its calculation or rounding rule unspecified.")
        if photo_classification and CLASSIFICATION_TERMS.search(text):
            reasons.append("The brief does not define how to handle unclear photos or how to check whether filled values are correct.")
        if reasons:
            flags.append({"criterionId": item["id"], "text": text, "severity": "Needs clarification", "reasons": reasons,
                          "question": _clarification_question(text, reasons, photo_classification)})
    return flags


def _clarification_question(text: str, reasons: list[str], photo_classification: bool = False) -> str:
    low = text.lower()
    if photo_classification and CLASSIFICATION_TERMS.search(text):
        return "What labels should clear photos produce, and what should happen with unclear or multi-item photos?"
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
    if re.search(r"\b(wardrobe|menu|navigation)\b", text, re.I):
        title = f"{item['id']}: Open the wardrobe area"
        steps = ["Open the application using a test account.", "Choose the wardrobe menu."]
        expected = "The wardrobe area opens and is ready for the next action."
    elif CLASSIFICATION_TERMS.search(text):
        title = f"{item['id']}: Check the details filled from a product photo"
        steps = ["Choose a synthetic photo with one clearly visible clothing item.", "Check the picture and the color, style, and category fields."]
        expected = "The picture is shown and the stated product detail fields are filled. Compare them with an agreed example for this photo."
    elif PHOTO_TERMS.search(text):
        title = f"{item['id']}: Choose and preview one supported product photo"
        steps = ["Open the wardrobe area.", "Choose a synthetic photo that contains one clothing item.", "Check that the selected picture is shown in the form."]
        expected = "The selected picture is shown and available for the product details flow."
    elif SAVE_TERMS.search(text):
        title = f"{item['id']}: Save and find the product in its wardrobe section"
        steps = ["Review the product details for the synthetic test item.", "Save the item.", "Open the section chosen by the product category."]
        expected = "The item appears in the section that matches the agreed category rule. Confirm the exact category mapping with the product owner."
    else:
        title = f"{item['id']}: {_sentence(text)}"
        steps = ["Open the relevant page or flow.", f"Exercise the behavior described by {item['id']} using representative synthetic data."]
        expected = f"The application satisfies this acceptance criterion: {text}"
    return {
        "id": "TS-" + slug.removeprefix("ac-"), "title": title, "acceptanceIds": [item["id"]],
        "kind": kind, "risk": risk, "preconditions": [f"The tester can access the {feature or 'target'} flow."],
        "steps": steps, "expectedResult": expected, "rationale": risk["rationale"], "source": "baseline"
    }


def _wardrobe_photo_scenarios(criteria: list[dict[str, str]], story: str, feature: str) -> list[dict[str, Any]]:
    """Add useful photo-flow cases when the brief clearly describes wardrobe classification."""
    context = " ".join([story, feature, *(item["text"] for item in criteria)])
    if not (PHOTO_TERMS.search(context) and WARDROBE_TERMS.search(context) and CLASSIFICATION_TERMS.search(context)):
        return []

    all_ids = [item["id"] for item in criteria]
    photo_ids = [item["id"] for item in criteria if PHOTO_TERMS.search(item["text"]) or re.search(r"\b(add|select|choose|click)\b", item["text"], re.I)]
    class_ids = [item["id"] for item in criteria if CLASSIFICATION_TERMS.search(item["text"]) or re.search(r"\b(photo|picture|image)\b", item["text"], re.I)]
    save_ids = [item["id"] for item in criteria if SAVE_TERMS.search(item["text"])]
    photo_ids = photo_ids or all_ids
    class_ids = class_ids or all_ids
    end_to_end_ids = all_ids
    risk_text = " ".join(criteria_by_id["text"] for criteria_by_id in criteria)
    risk = risk_for(risk_text)
    named_types = list(dict.fromkeys(match.group(0).lower() for match in CLOTHING_EXAMPLES.finditer(context)))
    type_setup = "Prepare one synthetic photo each for " + ", ".join(named_types) + "." if named_types else "Prepare synthetic photos for the approved clothing examples."
    scenarios = [
        {"title": "Happy path: add one clear clothing photo and save it", "acceptanceIds": end_to_end_ids,
         "kind": "happy path", "preconditions": ["Use a test account and synthetic clothing photos."],
         "steps": ["Open the wardrobe area.", "Choose a clear photo of one clothing item, such as a shirt.", "Check that the picture appears and the product detail fields are filled.", "Save the item.", "Open the matching wardrobe section and find the saved item."],
         "expectedResult": "The picture and filled details are shown, and the saved item appears in the section that matches the agreed category rule.",
         "rationale": "This follows the full user story. Confirm the category mapping and expected field values with the product owner."},
        {"title": "Positive: try the clothing types named in the brief", "acceptanceIds": class_ids,
         "kind": "positive", "preconditions": [type_setup],
         "steps": ["Add each photo separately.", "For each one, compare the filled category and color with an agreed expected label."],
         "expectedResult": "Each photo is shown and its detail fields are filled. The category matches the approved product examples.",
         "rationale": "The story names these clothing types but does not provide the approved category labels or color rules."},
        {"title": "Negative: submit an unreadable or unsupported photo", "acceptanceIds": photo_ids + [cid for cid in class_ids if cid not in photo_ids],
         "kind": "negative", "preconditions": ["Use a synthetic blurry photo and a non-clothing image."],
         "steps": ["Choose the blurry photo.", "Repeat with the non-clothing image.", "Check the response before saving."],
         "expectedResult": "Clarify the required behavior: should the app explain the problem, allow another photo, or permit manual entry? Do not treat a guessed category as confirmed.",
         "rationale": "Exploratory case. The brief does not define rejection, retry, or manual-entry behavior."},
        {"title": "Edge case: photo contains more than one clothing item", "acceptanceIds": class_ids,
         "kind": "edge case", "preconditions": ["Use a synthetic photo showing two different clothing items."],
         "steps": ["Choose the photo with two items.", "Review the picture and filled details before saving."],
         "expectedResult": "Clarify whether the app should ask the user to choose an item, create more than one item, or handle the photo another way.",
         "rationale": "Exploratory case. The brief does not say how multiple items in one photo should be handled."},
        {"title": "Edge case: replace a photo after details have been filled", "acceptanceIds": class_ids,
         "kind": "edge case", "preconditions": ["Prepare two different synthetic clothing photos."],
         "steps": ["Choose the first photo and wait for the fields to fill.", "Replace it with the second photo.", "Check the picture and all filled fields before saving."],
         "expectedResult": "The shown picture and filled values match the second photo. Confirm the expected values against approved examples.",
         "rationale": "Checks that old detected values do not stay in the form after a photo is replaced."},
        {"title": "Edge case: confirm the item remains after leaving and returning", "acceptanceIds": save_ids or end_to_end_ids,
         "kind": "edge case", "preconditions": ["A product has been saved with an agreed category."],
         "steps": ["Leave the wardrobe area.", "Return to the wardrobe and open the item's section."],
         "expectedResult": "The saved item is still present in the matching section with the saved details.",
         "rationale": "Checks saved data after the user leaves the flow. Confirm whether persistence across sign-out or app restart is also required."},
    ]
    for scenario in scenarios:
        scenario.update({"id": "", "risk": risk, "source": "local scenario design"})
    return scenarios


def _assign_local_ids(scenarios: list[dict[str, Any]], existing: set[str]) -> list[dict[str, Any]]:
    next_id = 1
    for scenario in scenarios:
        while f"TS-{next_id:02d}" in existing:
            next_id += 1
        scenario["id"] = f"TS-{next_id:02d}"
        existing.add(scenario["id"])
        next_id += 1
    return scenarios


def _sentence(text: str) -> str:
    result = text.strip().rstrip(".?!")
    return result[:180]


def _gherkin(product: str, feature: str, scenarios: list[dict[str, Any]]) -> str:
    name = feature or "The requested user journey"
    lines = [f"Feature: {name}", f"  As a user of {product or 'the application'}", "  I want the behavior in the acceptance criteria", "  So that the journey is predictable", ""]
    for scenario in scenarios:
        kind_tag = re.sub(r"[^a-z0-9]+", "-", scenario["kind"].lower()).strip("-")
        tags = " ".join([*("@" + cid.lower() for cid in scenario["acceptanceIds"]), "@" + scenario["id"].lower(), "@" + kind_tag, "@risk-" + scenario["risk"]["level"].lower()])
        lines += [f"  {tags}", f"  Scenario: {scenario['title']}"]
        for condition in scenario.get("preconditions", []):
            lines.append("    Given " + condition)
        for index, step in enumerate(scenario.get("steps", [])):
            if index == 0 and any(term in step.lower() for term in ("can access", "a product has", "use a test account", "prepare one synthetic")):
                keyword = "Given"
            elif index == 0:
                keyword = "When"
            else:
                keyword = "And"
            lines.append(f"    {keyword} {step}")
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
    local_additions = _assign_local_ids(_wardrobe_photo_scenarios(criteria, story, feature), {scenario["id"] for scenario in baseline})
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
                       "acceptanceIds": mapped, "kind": raw.get("kind") if raw.get("kind") in {"happy path", "positive", "negative", "edge case", "boundary", "security", "accessibility", "exploratory"} else "exploratory",
                       "risk": risk, "preconditions": [str(x)[:180] for x in raw_preconditions[:4]],
                       "steps": [str(x)[:240] for x in raw_steps[:8]],
                       "expectedResult": str(raw.get("expectedResult", "Review the observable result with the product owner."))[:400],
                       "rationale": str(raw.get("rationale", "AI-suggested addition; review before use."))[:240], "source": "ai"})
    scenarios = baseline + local_additions + extras
    ambiguities = analyze_ambiguity(criteria, story=story, feature=feature)
    traceability = []
    for item in criteria:
        ids = [s["id"] for s in scenarios if item["id"] in s["acceptanceIds"]]
        traceability.append({"criterionId": item["id"], "criterion": item["text"], "scenarioIds": ids, "covered": bool(ids)})
    return {"product": product or "Unspecified demo", "url": url, "feature": feature or "User journey", "story": story,
            "engine": engine, "criteria": criteria, "scenarios": scenarios, "ambiguities": ambiguities, "traceability": traceability,
            "coverage": round(sum(row["covered"] for row in traceability) / len(traceability) * 100) if traceability else 0,
            "riskSummary": {level: sum(s["risk"]["level"] == level for s in scenarios) for level in ["High", "Medium", "Low"]},
            "gherkin": _gherkin(product, feature, scenarios), "cypress": _cypress(product, url, feature, scenarios)}
