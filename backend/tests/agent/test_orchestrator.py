import base64
import hashlib
import json
import subprocess
from argparse import Namespace

import pytest

from scripts.agent.orchestrator import (
    OrchestrationError,
    RunState,
    apply_bundle,
    command_accept_plan,
    command_record_repair,
    command_record_verification,
    coverage_value,
    extract_agent_plan,
    is_application_file,
    is_allowed_test,
    make_bundle as build_bundle,
    read_state,
    stage_bundle,
    validate_bundle,
    validate_plan,
    write_state,
)


def make_plan(**overrides):
    plan = {
        "decision": "add_tests",
        "summary": "Add focused coverage for the changed validator behavior.",
        "file_decisions": [
            {
                "implementation_file": "backend/app/features/todos/validators.py",
                "decision": "add_tests",
                "reason": "The PR adds a validation branch.",
            }
        ],
        "targets": [
            {
                "implementation_file": "backend/app/features/todos/validators.py",
                "test_file": "backend/tests/features/todos/test_validators.py",
                "symbol": "validate_title",
                "reason": "The PR adds a new title validation branch.",
                "scenarios": ["Reject a title containing only whitespace."],
            }
        ],
        "skills_used": ["analyze-pr-changes", "backend-unit-tests"],
        "uncertainties": [],
    }
    plan.update(overrides)
    return plan


def make_bundle(path=None, content=b"def test_generated():\n    assert True\n", plan=None):
    plan = plan or make_plan()
    path = path or plan["targets"][0]["test_file"]
    return {
        "version": 1,
        "head_sha": "abc123",
        "changed_files": ["backend/app/features/todos/validators.py"],
        "plan": plan,
        "files": [
            {
                "path": path,
                "content_base64": base64.b64encode(content).decode("ascii"),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }


def test_validate_plan_accepts_targeted_backend_test():
    result = validate_plan(
        make_plan(),
        ["backend/app/features/todos/validators.py"],
    )

    assert result["decision"] == "add_tests"
    assert result["targets"][0]["test_file"].endswith("test_validators.py")


def test_is_allowed_test_requires_repository_test_naming_conventions():
    assert is_allowed_test("backend/tests/features/todos/test_validators.py")
    assert not is_allowed_test("backend/tests/features/todos/validators_test.py")
    assert not is_allowed_test("backend/tests/features/todos/helpers.py")
    assert is_allowed_test("frontend/src/features/todos/TodosPage.test.tsx")
    assert not is_allowed_test("frontend/src/features/todos/TodosPage.spec.tsx")


@pytest.mark.parametrize(
    "target_path",
    [
        "../outside.py",
        "backend/app/features/todos/validators.py",
        "frontend/src/features/todos/TodosPage.test.tsx",
    ],
)
def test_validate_plan_rejects_unsafe_or_unrelated_test_paths(target_path):
    plan = make_plan()
    plan["targets"][0]["test_file"] = target_path

    with pytest.raises(OrchestrationError):
        validate_plan(plan, ["backend/app/features/todos/validators.py"])


def test_validate_plan_rejects_target_outside_pull_request_diff():
    with pytest.raises(OrchestrationError, match="not part of the pull request diff"):
        validate_plan(make_plan(), ["backend/app/features/todos/router.py"])


def test_validate_plan_requires_a_decision_for_every_changed_file():
    with pytest.raises(OrchestrationError, match="one decision for every"):
        validate_plan(make_plan(), ["backend/app/features/todos/validators.py", "backend/app/factory.py"])


def test_validate_plan_rejects_targets_for_files_marked_skip():
    plan = make_plan()
    plan["file_decisions"][0]["decision"] = "skip"

    with pytest.raises(OrchestrationError, match="lacks an actionable decision"):
        validate_plan(plan, ["backend/app/features/todos/validators.py"])


def test_validate_plan_requires_a_target_for_every_actionable_file():
    plan = make_plan()
    changed = [
        "backend/app/features/todos/validators.py",
        "backend/app/features/todos/router.py",
    ]
    plan["file_decisions"].append(
        {
            "implementation_file": changed[1],
            "decision": "update_tests",
            "reason": "The changed route behavior needs updated assertions.",
        }
    )

    with pytest.raises(OrchestrationError, match="Every file marked"):
        validate_plan(plan, changed)


@pytest.mark.parametrize(
    ("decision", "targets", "file_decisions", "uncertainties", "expected"),
    [
        (
            "skip",
            [],
            [
                {
                    "implementation_file": "backend/app/features/todos/validators.py",
                    "decision": "skip",
                    "reason": "Existing tests already cover this behavior.",
                }
            ],
            [],
            False,
        ),
        (
            "report_uncertainty",
            [],
            [
                {
                    "implementation_file": "backend/app/features/todos/validators.py",
                    "decision": "report_uncertainty",
                    "reason": "Expected behavior is not specified.",
                }
            ],
            ["The intended behavior is unclear."],
            False,
        ),
        ("add_tests", [], None, [], True),
    ],
)
def test_validate_plan_enforces_decision_target_contract(
    decision, targets, file_decisions, uncertainties, expected
):
    plan = make_plan(
        decision=decision,
        targets=targets,
        uncertainties=uncertainties,
    )
    if file_decisions is not None:
        plan["file_decisions"] = file_decisions

    if expected:
        with pytest.raises(OrchestrationError, match="requires at least one"):
            validate_plan(plan, ["backend/app/features/todos/validators.py"])
    else:
        assert validate_plan(plan, ["backend/app/features/todos/validators.py"])["decision"] == decision


def test_extract_agent_plan_reads_last_assistant_message_from_jsonl():
    output = "\n".join(
        [
            '{"type":"session.info","id":"run-1"}',
            '{"type":"assistant.message","content":"not the final answer"}',
            '{"type":"assistant.message","content":"{\\"decision\\":\\"skip\\",\\"summary\\":\\"No tests needed.\\",\\"file_decisions\\":[],\\"targets\\":[],\\"skills_used\\":[],\\"uncertainties\\":[]}"}',
        ]
    )

    assert extract_agent_plan(output)["decision"] == "skip"


def test_extract_agent_plan_rejects_missing_assistant_response():
    with pytest.raises(OrchestrationError, match="did not contain"):
        extract_agent_plan('{"type":"tool.execution_start"}')


def test_run_state_limits_repair_to_one_attempt():
    state = RunState("abc123", ["backend/app/a.py"])
    state.advance("ANALYZE")
    state.advance("DECIDE")
    state.advance("GENERATE")
    state.advance("VERIFY")
    state.advance("REPAIR")
    state.advance("VERIFY")
    state.advance("FINALIZE")

    with pytest.raises(OrchestrationError, match="Invalid workflow transition"):
        state.advance("REPAIR")


def test_run_state_round_trip_rejects_inconsistent_repair_count():
    state = RunState("abc123", ["backend/app/a.py"])
    state.advance("ANALYZE")
    state.advance("DECIDE")
    state.advance("GENERATE")
    state.advance("VERIFY")
    state.advance("REPAIR")
    state.advance("VERIFY")

    serialized = state.to_dict()
    assert RunState.from_dict(serialized).current == "VERIFY"
    serialized["repair_attempts"] = 0
    with pytest.raises(OrchestrationError, match="does not match"):
        RunState.from_dict(serialized)


def test_agent_repair_state_machine_allows_one_repair_and_finalizes(tmp_path):
    state_path = tmp_path / "state.json"
    plan_path = tmp_path / "plan.json"
    outputs_path = tmp_path / "outputs.txt"
    state = RunState(
        "abc123",
        ["backend/app/features/todos/validators.py"],
    )
    state.advance("ANALYZE")
    state.advance("DECIDE")
    write_state(state_path, state)
    plan_path.write_text(json.dumps(make_plan()), encoding="utf-8")

    command_accept_plan(
        Namespace(
            state_file=str(state_path),
            plan_file=str(plan_path),
            github_output=str(outputs_path),
        )
    )
    assert read_state(state_path).current == "VERIFY"

    command_record_verification(
        Namespace(
            state_file=str(state_path),
            result="failed",
            github_output=str(outputs_path),
        )
    )
    assert read_state(state_path).current == "REPAIR"

    command_record_repair(
        Namespace(state_file=str(state_path), plan_file=str(plan_path))
    )
    assert read_state(state_path).current == "VERIFY"

    command_record_verification(
        Namespace(
            state_file=str(state_path),
            result="passed",
            github_output=str(outputs_path),
        )
    )
    finalized = read_state(state_path)
    assert finalized.current == "FINALIZE"
    assert finalized.repair_attempts == 1
    assert "next_step=repair" in outputs_path.read_text(encoding="utf-8")
    assert "next_step=finalize" in outputs_path.read_text(encoding="utf-8")


def test_validate_bundle_rejects_path_escape_and_hash_mismatch():
    with pytest.raises(OrchestrationError, match="Unsafe repository path"):
        validate_bundle(make_bundle("../outside.py"), "abc123")

    bundle = make_bundle()
    bundle["files"][0]["sha256"] = "0" * 64
    with pytest.raises(OrchestrationError, match="checksum mismatch"):
        validate_bundle(bundle, "abc123")


def test_validate_bundle_rejects_unplanned_file_and_empty_actionable_bundle():
    with pytest.raises(OrchestrationError, match="outside the test plan targets"):
        validate_bundle(make_bundle("backend/tests/test_other.py"), "abc123")

    bundle = make_bundle()
    bundle["files"] = []
    with pytest.raises(OrchestrationError, match="contains no test files"):
        validate_bundle(bundle, "abc123")


def test_validate_bundle_requires_changes_for_every_planned_target():
    bundle = make_bundle()
    second_implementation = "backend/app/features/todos/router.py"
    bundle["changed_files"].append(second_implementation)
    bundle["plan"]["file_decisions"].append(
        {
            "implementation_file": second_implementation,
            "decision": "add_tests",
            "reason": "The route adds a response branch.",
        }
    )
    bundle["plan"]["targets"].append(
        {
            "implementation_file": second_implementation,
            "test_file": "backend/tests/features/todos/test_router.py",
            "symbol": "list_todos",
            "reason": "The new route branch needs an assertion.",
            "scenarios": ["Return an empty list when no todos exist."],
        }
    )

    with pytest.raises(OrchestrationError, match="omits planned targets"):
        validate_bundle(bundle, "abc123")


def test_validate_bundle_rejects_mismatched_pr_head():
    with pytest.raises(OrchestrationError, match="different PR commit"):
        validate_bundle(make_bundle(), "new-sha")


def test_apply_bundle_writes_only_validated_test_file(tmp_path):
    bundle = make_bundle()

    apply_bundle(tmp_path, bundle, "abc123")

    assert (tmp_path / bundle["files"][0]["path"]).read_bytes() == base64.b64decode(
        bundle["files"][0]["content_base64"]
    )


def test_stage_bundle_stages_only_verified_artifact_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    existing = tmp_path / "backend" / "tests" / "test_existing.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "backend/tests/test_existing.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)

    bundle = make_bundle()
    generated = tmp_path / bundle["files"][0]["path"]
    generated.parent.mkdir(parents=True, exist_ok=True)
    content = base64.b64decode(bundle["files"][0]["content_base64"])
    generated.write_bytes(content)
    existing.write_text("def test_existing():\n    assert 1 == 1\n", encoding="utf-8")

    stage_bundle(tmp_path, bundle, "abc123")

    staged = subprocess.run(
        ["git", "-C", str(tmp_path), "diff", "--cached", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert staged == [bundle["files"][0]["path"]]

    generated.write_text("modified after verification\n", encoding="utf-8")
    with pytest.raises(OrchestrationError, match="changed before staging"):
        stage_bundle(tmp_path, bundle, "abc123")


def test_make_bundle_collects_only_test_changes(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    generated = tmp_path / "backend" / "tests" / "test_generated.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("def test_generated():\n    assert True\n", encoding="utf-8")
    plan = make_plan()
    plan["targets"][0]["test_file"] = "backend/tests/test_generated.py"

    bundle = build_bundle(
        tmp_path,
        "abc123",
        ["backend/app/features/todos/validators.py"],
        plan,
    )

    assert [item["path"] for item in bundle["files"]] == ["backend/tests/test_generated.py"]


def test_make_bundle_rejects_modified_non_test_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    source = tmp_path / "backend" / "app" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text("app = None\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "backend/app/main.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    source.write_text("app = object()\n", encoding="utf-8")

    with pytest.raises(OrchestrationError, match="outside the test allowlist"):
        build_bundle(
            tmp_path,
            "abc123",
            ["backend/app/main.py"],
            {
                "decision": "skip",
                "summary": "Skip.",
                "file_decisions": [
                    {
                        "implementation_file": "backend/app/main.py",
                        "decision": "skip",
                        "reason": "No test changes are needed.",
                    }
                ],
                "targets": [],
                "skills_used": ["analyze-pr-changes"],
                "uncertainties": [],
            },
        )


def test_apply_bundle_rejects_changed_pr_diff(tmp_path):
    with pytest.raises(OrchestrationError, match="does not match the current PR diff"):
        apply_bundle(
            tmp_path,
            make_bundle(),
            "abc123",
            ["backend/app/features/todos/router.py"],
        )


def test_frontend_coverage_summary_returns_statement_percentage(tmp_path):
    report = tmp_path / "coverage-summary.json"
    report.write_text(
        '{"total":{"statements":{"total":20,"covered":15,"pct":75}}}',
        encoding="utf-8",
    )

    assert coverage_value(report, "frontend") == 75


def test_backend_coverage_report_returns_statement_percentage(tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text('{"totals":{"percent_covered":42.5}}', encoding="utf-8")

    assert coverage_value(report, "backend") == 42.5


@pytest.mark.parametrize(
    ("path", "application", "test"),
    [
        ("backend/app/features/todos/router.py", True, False),
        ("frontend/src/features/todos/TodosPage.tsx", True, False),
        ("frontend/src/features/todos/TodosPage.test.tsx", False, True),
        ("frontend/src/features/todos/TodosPage.stories.tsx", False, False),
        ("backend/tests/features/todos/test_router.py", False, True),
        ("backend/tests/conftest.py", False, False),
    ],
)
def test_classifies_application_and_test_paths(path, application, test):
    assert is_application_file(path) is application
    assert is_allowed_test(path) is test
