import unittest
from generator import analyze_ambiguity, build_artifacts, parse_criteria
from evaluate import run_evaluation


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "product": "SauceDemo sample shop",
            "url": "https://www.saucedemo.com/",
            "feature": "Checkout a selected product",
            "story": "As a shopper, I want to finish a purchase.",
            "criteria": [
                "AC-01 | The cart shows each selected product with the same name and price as the inventory page.",
                "AC-02 | Checkout cannot continue when Postal Code is empty; a visible error message is shown.",
                "AC-03 | The total equals the item subtotal plus tax."
            ],
        }

    def test_all_criteria_have_traceable_baseline_scenario(self):
        result = build_artifacts(self.payload)
        self.assertEqual(result["coverage"], 100)
        self.assertEqual(sum(scenario["source"] == "baseline" for scenario in result["scenarios"]), 3)
        self.assertTrue(all(row["covered"] for row in result["traceability"]))
        kinds = {scenario["kind"] for scenario in result["scenarios"]}
        self.assertTrue({"happy path", "positive", "negative", "edge case", "boundary"} <= kinds)

    def test_preparsed_criteria_can_be_analyzed_again(self):
        parsed = parse_criteria(self.payload["criteria"])
        result = build_artifacts({**self.payload, "criteria": parsed})
        self.assertEqual(result["criteria"], parsed)
        self.assertIn("The cart shows each selected product", result["scenarios"][0]["title"])
        self.assertNotIn("{'id':", result["scenarios"][0]["title"])

    def test_vague_validation_is_flagged(self):
        criteria = parse_criteria(["AC-01 | Required fields are validated."])
        flags = analyze_ambiguity(criteria)
        self.assertEqual(flags[0]["criterionId"], "AC-01")
        self.assertIn("exact message", flags[0]["question"])

    def test_explicit_money_formula_is_not_flagged_as_ambiguous(self):
        criteria = parse_criteria(["AC-01 | The total equals the item subtotal plus tax."])
        self.assertEqual(analyze_ambiguity(criteria), [])

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            parse_criteria(["AC-01 | First", "AC-01 | Second"])

    def test_sample_generates_gherkin_and_cypress_drafts(self):
        import json
        from pathlib import Path
        sample = json.loads((Path(__file__).parents[1] / "public/examples/saucedemo-checkout.json").read_text(encoding="utf-8"))
        result = build_artifacts(sample)
        self.assertIn("Feature: Checkout a selected product", result["gherkin"])
        self.assertIn("@ac-01", result["gherkin"])
        self.assertIn("data-test=", result["cypress"])
        self.assertIn("Traceability: AC-01", result["cypress"])

    def test_search_plan_adds_no_results_and_reset_cases(self):
        result = build_artifacts({
            "product": "Sample Shop",
            "feature": "Search products",
            "story": "As a shopper, I want to search and filter products.",
            "criteria": ["AC-01 | Search results show matching products.", "AC-02 | Filters narrow the product list."],
        })
        titles = [scenario["title"] for scenario in result["scenarios"]]
        self.assertTrue(any("no matches" in title for title in titles))
        self.assertTrue(any("clear search" in title for title in titles))
        self.assertEqual(result["coverage"], 100)

    def test_form_plan_marks_unknown_validation_and_limits_for_review(self):
        result = build_artifacts({
            "product": "Sample Profile",
            "feature": "Edit profile form",
            "story": "As a user, I want to edit my profile details.",
            "criteria": ["AC-01 | Profile form updates the saved details."],
        })
        scenarios = result["scenarios"]
        self.assertTrue(any(scenario["kind"] == "happy path" for scenario in scenarios))
        self.assertTrue(any(scenario["kind"] == "negative" and "Confirm which invalid value" in scenario["expectedResult"] for scenario in scenarios))
        self.assertTrue(any(scenario["kind"] == "boundary" for scenario in scenarios))

    def test_evaluation_fixtures(self):
        result = run_evaluation()
        self.assertEqual(result["caseCount"], 5)
        self.assertEqual(result["criterionCoverage"], 100)
        self.assertEqual(result["ambiguityRecall"], 100)
        self.assertTrue(all(case["pass"] for case in result["details"]))


if __name__ == "__main__":
    unittest.main()
