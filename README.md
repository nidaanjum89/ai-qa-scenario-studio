# AI QA Scenario Studio

This demo helps turn a feature idea into a QA plan. It uses a sample shop called SauceDemo.

## What it does

1. Add a user story and its acceptance criteria.
2. Generate happy paths, positive checks, negative cases, and edge cases where the brief gives enough clues.
3. Review unclear wording and possible risks.
4. Mark each criterion as reviewed or needing changes.
5. View the scenarios as Gherkin or a Cypress code draft.
6. Save plans and reviews in a project memory on this computer.

The main goal is test planning. The Cypress code is only a starting point.

## Try it

You need Python 3.10 or newer. No extra packages are needed.

```bash
python3 app.py
```

Then open <http://127.0.0.1:8000>. A SauceDemo checkout example is ready to use.

## Project memory

- Each generated plan is saved in the selected project.
- Review choices are saved too. You can open an older plan later.
- Use **Back up plans** to save every plan and review in the selected project to one file. Use **Load backup** to make a new project copy from that file.
- Use **Download plan + code** to get a readable file for the plan you are looking at now. It includes the test cases and code drafts.
- The database stays on this computer. This demo does not sync projects between people. Team sharing needs a shared server and sign-in.
- The database file is not added to GitHub.

## Important to know

- This demo does not run tests against SauceDemo or check that results match the real site.
- The Cypress draft is basic. Its tests are skipped until someone reviews and completes them. Fit the code to your team's page objects, test data, login setup, and selectors before using it.
- Local scenario ideas use simple rules. For example, a clothing-photo flow gets cases for a clear photo, common clothing types, an unclear photo, more than one item, and checking a saved item again.
- Cases for behavior the brief does not explain are marked for review. They are questions to discuss, not facts about the real product.
- Risk and unclear-wording checks use simple rules. They can miss things.
- Only approved examples from the selected project can be shared with the AI for future suggestions. Review an example before approving it.

## Optional AI suggestions

The demo works without an AI key. It uses local rules and flow-specific examples in that mode.

To ask an OpenAI model for extra ideas, set your API key before starting the app:

```bash
export OPENAI_API_KEY="your-key"
python3 app.py
```

When AI suggestions are on, the current brief and approved examples from the selected project are sent to the OpenAI API. The AI is asked to add useful happy, positive, negative, or edge cases without repeating the local scenarios. Use sample information only. Do not enter employer, customer, personal, or confidential data.

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 evaluate.py
```

Unit tests check that the app's own rules and memory work. The evaluation uses five sample briefs. These checks do not measure real-world QA quality or AI accuracy.
