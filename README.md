# AI QA Scenario Studio

**A small, review-first QA planning workbench.** Turn a synthetic user story into risk-aware scenarios, acceptance-criteria traceability, Gherkin, and a Cypress test skeleton. The starter brief uses [SauceDemo](https://www.saucedemo.com/), a public sample shop used for automation practice; Sauce Labs also uses it in its [official sample scripts](https://docs.saucelabs.com/web-apps/automated-testing/selenium/sample-scripts/).

> This is a portfolio prototype. It does not crawl the target website or verify that generated expectations match the live product. Treat each artifact as a draft for human review.

## What it demonstrates

- **Risk-based planning:** gives each criterion a transparent impact/likelihood heuristic and explains why it was ranked.
- **Traceability:** creates one baseline scenario for every acceptance criterion and shows the mapping.
- **Ambiguity checks:** flags a small set of subjective phrases, underspecified validation, and unclear money calculations, then suggests a question for the product owner.
- **Gherkin and Cypress drafts:** exports feature scenarios and a JavaScript spec skeleton with tests skipped pending review. For the SauceDemo sample it uses example `data-test` locators; add login/setup, verify the selectors and behavior, then unskip tests before running.
- **Human review:** mark criteria as reviewed or needing changes in the browser. Review marks stay in memory for the current page only and are not submitted or saved.
- **Optional AI suggestions:** a server-side OpenAI Responses API call can suggest up to four additional scenarios. Local traceability and risk rules still run around those additions. The API key never goes to the browser.
- **Small evaluation set:** synthetic fixtures measure criterion coverage and ambiguity-flag recall. This is a repeatable check of the demo rules, not a measure of real-world QA quality or model accuracy.

## Run locally

Requires Python 3.10 or newer. No package installation is needed.

```bash
python3 app.py
```

Open <http://127.0.0.1:8000>. By default, the app runs in local-rules mode with the SauceDemo checkout brief preloaded.

## Optional AI mode

The app remains useful without an API key. To enable AI-proposed additional scenarios, set your key in the server environment before starting it:

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="model-available-to-your-account"
python3 app.py
```

`OPENAI_MODEL` defaults to `gpt-4.1-mini`; set a model available to your account if that default is not enabled. The browser never receives the key. Inputs are not stored by this app; when AI mode is enabled, the brief is sent to the configured OpenAI API. Use only synthetic, non-confidential examples. The integration requests `store: false`, but configure and review your own API account's data settings before using it.

## Checks and evaluation

```bash
python3 -m unittest discover -s tests -v
python3 evaluate.py
```

The evaluation uses five synthetic fixtures. It reports requirement coverage and whether known ambiguous criteria were flagged. Its denominator is the hand-authored expected flags in that tiny set; it should not be described as an ATS score, test-quality score, or general AI benchmark.

## Project map

```text
app.py                         Local HTTP server and API
generator.py                   Deterministic analysis and artifact generation
 ai_provider.py                Optional server-side Responses API adapter
evaluate.py                    Synthetic evaluation runner
data/evaluation_cases.json     Hand-authored eval fixtures
public/index.html              Accessible single-page workbench
public/app.js                  Form, tabs, review, copy, and export behavior
public/styles.css              Responsive visual system
public/examples/                Synthetic SauceDemo checkout brief
tests/test_generator.py        Standard-library unit tests
```

## Current limitations

- The wording checks are intentionally small and will miss context-dependent ambiguity.
- Risk scoring is heuristic. A team should replace the keywords and scoring rules with its own risk model.
- AI suggestions can be incomplete or incorrect. The deterministic baseline preserves at least one mapping per criterion, but does not prove semantic correctness.
- Cypress output is a starting point. Authentication setup, test data, exact selectors, and site behavior need review before execution.
- No requirement, review state, or generated artifact is stored by the app.

## Privacy and safety

Do not paste employer, customer, personal, credential, or production data. Local mode keeps generation in the local Python process. AI mode sends the brief to the configured API. The server binds to `127.0.0.1` by default and does not log prompt contents or save requests to disk.
