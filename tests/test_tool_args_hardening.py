"""Tests for hardened tool argument handling (no Python interpolation)."""

import io
import json
from contextlib import redirect_stdout

import pytest

from ai_jup.handlers import _build_tool_execution_code, _validate_tool_args


def test_validate_tool_args_rejects_invalid_key():
    with pytest.raises(ValueError, match="Invalid tool argument name"):
        _validate_tool_args({"bad-key": 1})


def test_build_tool_execution_code_handles_json_bool_and_null():
    def tool(flag: bool, opt=None):
        return {"flag": flag, "opt": opt}

    code = _build_tool_execution_code("tool", {"flag": True, "opt": None}, timeout=5)

    stdout = io.StringIO()
    scope = {"tool": tool}
    with redirect_stdout(stdout):
        exec(code, scope, scope)

    last_line = stdout.getvalue().strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["status"] == "success"

    result = payload["result"]
    assert result["type"] == "text"
    assert "True" in result["content"]
    assert "None" in result["content"]

