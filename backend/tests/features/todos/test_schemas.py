import pytest
from pydantic import ValidationError

from app.features.todos.schemas import Priority, TodoCreate, TodoUpdate


def test_create_applies_defaults():
    todo = TodoCreate(title="Write tests")

    assert todo.description == ""
    assert todo.priority == Priority.medium
    assert todo.due_date is None
    assert todo.completed is False


def test_create_strips_whitespace_from_title():
    assert TodoCreate(title="  Write tests  ").title == "Write tests"


@pytest.mark.parametrize("title", ["", "   ", "x" * 121])
def test_create_rejects_invalid_title(title):
    with pytest.raises(ValidationError):
        TodoCreate(title=title)


def test_create_rejects_unknown_fields_and_invalid_priority():
    with pytest.raises(ValidationError):
        TodoCreate(title="a", extra="nope")
    with pytest.raises(ValidationError):
        TodoCreate(title="a", priority="urgent")


def test_create_requires_strict_boolean_for_completed():
    with pytest.raises(ValidationError):
        TodoCreate(title="a", completed="yes")


def test_update_rejects_empty_patch():
    with pytest.raises(ValidationError, match="at least one field"):
        TodoUpdate()


def test_update_rejects_null_for_required_fields():
    with pytest.raises(ValidationError, match="cannot be null"):
        TodoUpdate(title=None)


def test_update_allows_explicit_null_due_date():
    patch = TodoUpdate(due_date=None)

    assert patch.model_fields_set == {"due_date"}
    assert patch.due_date is None
