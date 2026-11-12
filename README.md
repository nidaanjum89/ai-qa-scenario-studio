# AI QA Scenario Studio

This demo helps turn a feature idea into a simple QA plan. It uses a sample online shop called SauceDemo.

## What it does

1. You enter a user story and its acceptance criteria.
2. The studio suggests test scenarios and links each one to a criterion.
3. It highlights risks and wording that may need clarification.
4. You can review the suggestions and mark criteria as reviewed or needing changes.
5. You can also view Gherkin scenarios and a Cypress code draft.

The main focus is test planning. The Cypress code is an optional starting point.

## Try it

You need Python 3.10 or newer. No extra packages are needed.

```bash
python3 app.py
```

Then open <http://127.0.0.1:8000>. A SauceDemo checkout example is loaded for you.

## Important to know

- This demo does not run tests against SauceDemo or check that the suggested results match the real site.
- The Cypress draft is basic. Its tests are skipped until a person reviews and completes them. Adapt it to your project's page objects, test data, login setup, and selectors before using it.
- Review every suggestion. The risk ratings and unclear-wording checks use simple rules and can miss things.
- Your brief and review marks are not saved by the app.

## Optional AI suggestions

The demo works without an AI key. In that mode, it uses simple local rules.

To ask an OpenAI model for a few extra scenario ideas, set your API key before starting the app:

```bash
export OPENAI_API_KEY="your-key"
python3 app.py
```

When AI suggestions are enabled, the brief is sent to the OpenAI API. Use sample information only. Do not enter employer, customer, personal, or confidential data.

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 evaluate.py
```

The unit tests check that the studio's own logic works. The evaluation checks five sample briefs. These checks do not measure the quality of real-world testing or AI results.
