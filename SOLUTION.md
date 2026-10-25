# PR Test Agent

## One agent, reusable skills

There is exactly one custom AI agent: `.github/agents/test-generation.agent.md`. It analyzes the diff, decides whether to add/update/skip tests or report uncertainty, selects reusable skills, writes tests, and reviews its proposed changes. If verification fails, the same agent definition gets one bounded repair turn. These are stages/turns of one agent identity, not separate agents or subagents.

Reusable skills are instruction bundles loaded by that same agent:

- `.github/skills/analyze-pr-changes/SKILL.md`
- `.github/skills/backend-unit-tests/SKILL.md`
- `.github/skills/frontend-unit-tests/SKILL.md`
- `.github/skills/verify-generated-tests/SKILL.md`

GitHub Actions and `scripts/agent/orchestrator.py` are deterministic orchestration, not agents. They control states, validate the agent plan, enforce changed-file boundaries, run tests, cap repairs, and publish verified results.

## Implemented architecture

```text
Same-repository pull request
           |
           v
pull_request_target workflow (trusted workflow from base revision)
  |
  +--> baseline job: run tests at base SHA; no write/Copilot permissions
  |
  +--> generate job: one custom agent invocation; read-only GitHub token
  |       - custom agent and skills loaded from trusted base checkout
  |       - PR source is mounted separately for read/edit tools
  |       - structured plan validated and test-only bundle produced
  |
  +--> separate backend/frontend verify jobs: apply validated bundle and test PR code
  |       - no Copilot or write permission
  |       - collect test outcomes and base-vs-PR coverage delta
  +--> failure-log job: read verification logs and pass bounded diagnostics to repair
  |
  +--> optional repair job: same custom agent, one additional turn
  |       - only if baseline passes and generated tests fail
  +--> verify-repair jobs: rerun both suites without write credentials
           |
           v
Separate publish job (contents/issues write)
  - verify expected PR head SHA is unchanged
  - validate artifact and apply only permitted test files
  - commit tests to the PR branch only after passing gates
  - update one PR comment and workflow summary
```

`.github/workflows/ci.yml` separately runs backend and frontend tests for every pull request, including forks, without any Copilot or write permissions. The agent workflow does not grant trusted credentials to fork code.

### Deterministic orchestrator

`scripts/agent/orchestrator.py` implements the explicit states:

```text
INITIALIZE -> ANALYZE -> DECIDE -> GENERATE -> VERIFY
                                      ^           |
                                      |           +-> FINALIZE
                                      +-- REPAIR -+
```

The orchestrator validates a JSON plan containing an overall decision, a decision and rationale for every changed implementation file, target test paths, scenarios, skills used, and uncertainties. It rejects paths outside the PR diff or test allowlist, malformed plans, oversized artifacts, checksum mismatches, and stale PR heads. State validation enforces a maximum of one repair attempt.

The generated artifact contains only allowlisted test file contents, checksums, the validated plan, and the PR head SHA. The privileged job uses trusted orchestration code from the base revision, re-validates the artifact and PR diff, and never runs the PR's tests or other code.

### Job permissions and trust boundaries

- The workflow uses `pull_request_target` so its workflow definition comes from the base revision. Fork PRs are skipped by this agent workflow.
- Baseline and verification jobs have read-only checkout permissions, do not persist checkout credentials, and do not receive Copilot credentials or write permissions. Backend and frontend verification run in separate jobs.
- The failure-log job has only `actions: read`; it retrieves logs as data and uploads a bounded artifact. The repair agent receives that artifact without the `actions: read` permission.
- The generation/repair jobs have `contents: read` and `copilot-requests: write`; they do not run PR code. Copilot is started in a temporary workspace containing only the trusted agent and skills. It has only read, search, and edit tools, and test-only edits are checked before packaging.
- The publication job has write permissions, but does not execute the PR code. It consumes a bounded JSON artifact, checks that the PR head has not moved, and stages only files present in the validated artifact.
- The test commit uses a push lease against the exact PR head SHA, preventing a concurrent branch update from being overwritten after the API check.
- The publish job can still push only to the same-repository PR branch. Any failed baseline/test check, invalid artifact, changed PR head, or failed guard prevents a generated-test commit.
- Fork PRs are tested by `.github/workflows/ci.yml`; no Copilot or write token is exposed to their code.

## Running and prerequisites

1. Push the repository to GitHub and enable Actions.
2. Enable Copilot CLI use for Actions billing in the organization policy if required.
3. Allow the job permissions declared in `.github/workflows/pr-test-agent.yml`: `contents: read/write`, `issues: write`, `pull-requests: read`, and `copilot-requests: write` in their respective jobs.
4. Open or update a PR from a branch in the same repository.

The workflow runs on PR open/reopen, synchronization, and ready-for-review. It uses the built-in `GITHUB_TOKEN`; no PAT is required. The Copilot CLI is installed in the agent jobs.

### Bulk coverage run (manual)

`.github/workflows/bulk-test-agent.yml` is a `workflow_dispatch` workflow that treats every application file in the selected scope (`all`, `backend`, or `frontend`) as changed. It uses the same agent, skills, and orchestrator (`prepare --all-files`, `prompt --bulk`), so the agent adds or updates tests where coverage is weak and skips files that are already covered. Test execution stays in token-free jobs; the publisher commits the verified tests to a new `agent/coverage-<run>` branch and opens a pull request with the per-file decisions and the before/after coverage. Run it from **Actions → Bulk test agent → Run workflow** (the file must exist on the default branch for the button to appear). The repository setting **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests** must be enabled. Pull requests created with `GITHUB_TOKEN` do not trigger other workflows, so close and reopen the PR (or push to it) to start `ci.yml`. Bulk mode has no repair turn: if the generated tests fail, nothing is published and the verification logs explain why.

## Local validation and observed baseline

The base application currently has 21 backend tests and 18 frontend tests. This change adds unit tests only for the new agent orchestrator; it does not add tests for unrelated application features. The agent's PR workflow reports the base and PR coverage values and their difference when it runs. Coverage is diagnostic, not a gate.

The orchestrator's focused unit tests are in `backend/tests/agent/test_orchestrator.py`. They cover plan validation, state transitions, repair limits, path allowlists, bundle hashes, stale SHAs, and coverage summaries. Run them from the repository root:

```sh
python -m pytest --noconftest -c backend/pyproject.toml backend/tests/agent/test_orchestrator.py
```

The orchestrator tests can be run with the command above. The application's existing complete backend suite can be run from `backend/` with `python -m pytest`; the frontend suite can be run from `frontend/` with `npm test`.

## Example run (illustrative, not yet executed on GitHub)

For a PR that changes `backend/app/features/todos/validators.py` with a new title-validation branch, the deterministic diff classifier passes the file to the single `test-generation` agent. An illustrative plan would decide `add_tests` because the new behavior needs direct boundary coverage, target `backend/tests/features/todos/test_validators.py`, and include a whitespace-only title scenario. The plan records `analyze-pr-changes`, `backend-unit-tests`, and `verify-generated-tests` as its skills. The orchestrator validates the response and packages only the targeted backend test file. Separate verification jobs run pytest and Vitest; the publisher reports their base-versus-PR statement-coverage delta. If generated tests fail while the base suites pass, the same agent receives bounded logs for one repair turn; the repaired tests are rerun. Only passing results can reach the publisher. The publisher checks the PR head SHA, stages only files from the verified artifact, commits tests to the PR branch, and updates the PR comment with per-file decisions, test outcomes, skills, uncertainties, and coverage. This is an architecture example, not a claimed agent run; a real GitHub run has not yet been executed.

## Limitations and production follow-ups

- Bulk mode is capped at 200 application files and a 50-file test bundle per run; use the `scope` input to split larger runs. It does not run a repair turn.
- Only same-repository PRs receive agent generation and the test commit. Fork PRs are intentionally skipped.
- The repair budget is one turn. A failing repair is reported but never committed.
- The model may still generate incorrect tests; passing tests and coverage are not proof of test quality. Human review is required.
- Coverage deltas are diagnostic and do not enforce a threshold.
- GitHub Actions are referenced by major version in this MVP. A production deployment should pin reviewed immutable action SHAs, add guard/orchestrator tests to required CI, consider a protected approval path for write operations, and add explicit billing/rate monitoring.
