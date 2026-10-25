---
name: frontend-unit-tests
description: "Use when adding or updating React and TypeScript unit tests for frontend changes in frontend/src, using Vitest and Testing Library."
---

# Frontend unit tests

1. Read nearby tests, `frontend/src/test/setup.ts`, and relevant fixtures before adding mocks.
2. Place tests beside the implementation using the existing `.test.ts` or `.test.tsx` naming convention.
3. Use Vitest and Testing Library patterns already present in the repository. Prefer user-visible behavior and accessible queries.
4. Cover meaningful success, error, empty, and boundary states appropriate to the changed behavior.
5. Keep tests deterministic; do not call live APIs or add dependencies.
6. Do not modify production code or dependency configuration to make a test pass.
7. The workflow verifies changes with `npm run test:coverage` from `frontend/`; do not claim the command passed before that step runs.
