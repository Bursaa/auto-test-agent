---
name: verify-generated-tests
description: "Use after creating or updating PR tests to review their scope, correctness, and likely reliability before deterministic workflow verification."
---

# Review generated tests

1. Confirm every changed file is a test file in the allowed backend or frontend test directories.
2. Check that each test has a meaningful behavioral assertion and does not duplicate nearby coverage.
3. Check for brittle timing, network access, real credentials, random outcomes, and assertions tied to incidental implementation details.
4. Check that each changed implementation file has an explicit decision and rationale in the plan.
5. Do not alter application files, workflow files, or dependency manifests.
6. Summarize any uncertainty. The workflow, not this review, runs pytest and Vitest and reports their actual exit statuses.
