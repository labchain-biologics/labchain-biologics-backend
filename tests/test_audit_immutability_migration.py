"""Tests for audit immutability migration SQL."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _load_migration_module() -> ModuleType:
    path = Path("alembic/versions/0002_audit_immutability.py")
    spec = importlib.util.spec_from_file_location("audit_immutability_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_creates_immutability_function_and_triggers() -> None:
    module = _load_migration_module()
    with patch.object(module.op, "execute") as execute:
        module.upgrade()
    statements = " ".join(str(call.args[0]) for call in execute.call_args_list)
    assert "prevent_audit_logs_mutation" in statements
    assert "trg_prevent_audit_logs_update" in statements
    assert "trg_prevent_audit_logs_delete" in statements


def test_downgrade_drops_immutability_function_and_triggers() -> None:
    module = _load_migration_module()
    with patch.object(module.op, "execute") as execute:
        module.downgrade()
    statements = " ".join(str(call.args[0]) for call in execute.call_args_list)
    assert "DROP TRIGGER IF EXISTS trg_prevent_audit_logs_delete" in statements
    assert "DROP TRIGGER IF EXISTS trg_prevent_audit_logs_update" in statements
    assert "DROP FUNCTION IF EXISTS prevent_audit_logs_mutation" in statements
