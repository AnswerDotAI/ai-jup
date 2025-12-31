"""Tests for fastcore.tools integration with ai-jup.

These tests verify that fastcore.tools functions work correctly with ai-jup's
tool calling infrastructure. The tests check:
1. Function introspection produces valid tool schemas
2. Tool building creates proper Anthropic-compatible definitions
3. Functions can be called with the expected arguments
4. Real fastcore.tools functions have the required metadata

The tests use the ACTUAL fastcore.tools functions, not mocks, to ensure
real-world compatibility.

fastcore is a required dependency (see pyproject.toml).
"""

import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastcore.tools import view, rg, sed, create, str_replace, insert

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFastcoreToolsMetadata:
    """Verify fastcore.tools functions have required metadata for AI tool use."""

    def test_view_has_docstring(self):
        """view() must have a docstring for tool description."""
        assert view.__doc__ is not None
        assert len(view.__doc__) > 0

    def test_view_has_type_annotations(self):
        """view() must have type annotations for schema generation."""
        sig = inspect.signature(view)
        # path parameter must have annotation
        assert sig.parameters["path"].annotation != inspect.Parameter.empty

    def test_rg_has_docstring(self):
        """rg() must have a docstring for tool description."""
        assert rg.__doc__ is not None
        assert len(rg.__doc__) > 0

    def test_rg_has_type_annotations(self):
        """rg() must have type annotations for schema generation."""
        sig = inspect.signature(rg)
        assert sig.parameters["argstr"].annotation != inspect.Parameter.empty

    def test_create_has_docstring(self):
        """create() must have a docstring for tool description."""
        assert create.__doc__ is not None
        assert len(create.__doc__) > 0

    def test_create_has_type_annotations(self):
        """create() must have type annotations for schema generation."""
        sig = inspect.signature(create)
        assert sig.parameters["path"].annotation != inspect.Parameter.empty
        assert sig.parameters["file_text"].annotation != inspect.Parameter.empty

    def test_str_replace_has_docstring(self):
        """str_replace() must have a docstring for tool description."""
        assert str_replace.__doc__ is not None
        assert len(str_replace.__doc__) > 0

    def test_str_replace_has_type_annotations(self):
        """str_replace() must have type annotations for schema generation."""
        sig = inspect.signature(str_replace)
        assert sig.parameters["path"].annotation != inspect.Parameter.empty
        assert sig.parameters["old_str"].annotation != inspect.Parameter.empty
        assert sig.parameters["new_str"].annotation != inspect.Parameter.empty


class TestFunctionIntrospection:
    """Test that ai-jup's introspection logic works on fastcore.tools."""

    def _get_function_info(self, func):
        """Replicate ai-jup's kernel introspection logic for a function."""
        sig = str(inspect.signature(func))
        doc = inspect.getdoc(func) or "No documentation"
        params = {}
        
        for pname, param in inspect.signature(func).parameters.items():
            pinfo = {"type": "string", "description": pname}
            if param.annotation != inspect.Parameter.empty:
                ann = param.annotation
                if hasattr(ann, "__name__"):
                    pinfo["type"] = ann.__name__
                elif hasattr(ann, "__origin__"):
                    pinfo["type"] = str(ann)
            if param.default != inspect.Parameter.empty:
                pinfo["default"] = repr(param.default)
            params[pname] = pinfo
        
        return {
            "name": func.__name__,
            "signature": sig,
            "docstring": doc[:500],
            "parameters": params
        }

    def test_view_introspection(self):
        """Introspecting view() produces valid function info."""
        info = self._get_function_info(view)
        
        assert info["name"] == "view"
        assert "path" in info["signature"]
        assert len(info["docstring"]) > 0
        assert "path" in info["parameters"]
        # path should be typed as str
        assert info["parameters"]["path"]["type"] == "str"

    def test_rg_introspection(self):
        """Introspecting rg() produces valid function info."""
        info = self._get_function_info(rg)
        
        assert info["name"] == "rg"
        assert "argstr" in info["parameters"]
        assert info["parameters"]["argstr"]["type"] == "str"

    def test_create_introspection(self):
        """Introspecting create() produces valid function info."""
        info = self._get_function_info(create)
        
        assert info["name"] == "create"
        assert "path" in info["parameters"]
        assert "file_text" in info["parameters"]
        # Both should be str type
        assert info["parameters"]["path"]["type"] == "str"
        assert info["parameters"]["file_text"]["type"] == "str"

    def test_str_replace_introspection(self):
        """Introspecting str_replace() produces valid function info."""
        info = self._get_function_info(str_replace)
        
        assert info["name"] == "str_replace"
        assert "path" in info["parameters"]
        assert "old_str" in info["parameters"]
        assert "new_str" in info["parameters"]


class TestToolSchemaBuilding:
    """Test that tool schemas are built correctly for Anthropic API."""

    def _build_tool_schema(self, func_info):
        """Replicate ai-jup's tool schema building logic."""
        params = func_info.get("parameters", {})
        return {
            "name": func_info["name"],
            "description": func_info.get("docstring", f"Call the {func_info['name']} function"),
            "input_schema": {
                "type": "object",
                "properties": params,
                "required": list(params.keys())
            }
        }

    def _get_function_info(self, func):
        """Get function info (same as above)."""
        sig = str(inspect.signature(func))
        doc = inspect.getdoc(func) or "No documentation"
        params = {}
        
        for pname, param in inspect.signature(func).parameters.items():
            pinfo = {"type": "string", "description": pname}
            if param.annotation != inspect.Parameter.empty:
                ann = param.annotation
                if hasattr(ann, "__name__"):
                    pinfo["type"] = ann.__name__
            if param.default != inspect.Parameter.empty:
                pinfo["default"] = repr(param.default)
            params[pname] = pinfo
        
        return {
            "name": func.__name__,
            "signature": sig,
            "docstring": doc[:500],
            "parameters": params
        }

    def test_view_tool_schema(self):
        """view() produces a valid Anthropic tool schema."""
        info = self._get_function_info(view)
        schema = self._build_tool_schema(info)
        
        assert schema["name"] == "view"
        assert "description" in schema
        assert len(schema["description"]) > 0
        assert schema["input_schema"]["type"] == "object"
        assert "path" in schema["input_schema"]["properties"]

    def test_create_tool_schema(self):
        """create() produces a valid Anthropic tool schema."""
        info = self._get_function_info(create)
        schema = self._build_tool_schema(info)
        
        assert schema["name"] == "create"
        assert "path" in schema["input_schema"]["properties"]
        assert "file_text" in schema["input_schema"]["properties"]
        # Both path and file_text should be required
        assert "path" in schema["input_schema"]["required"]
        assert "file_text" in schema["input_schema"]["required"]

    def test_schema_is_json_serializable(self):
        """Tool schemas must be JSON serializable for API calls."""
        info = self._get_function_info(view)
        schema = self._build_tool_schema(info)
        
        # This should not raise
        json_str = json.dumps(schema)
        assert len(json_str) > 0
        
        # And should round-trip correctly
        parsed = json.loads(json_str)
        assert parsed["name"] == "view"


class TestActualToolExecution:
    """Test that fastcore.tools functions actually work when called."""

    def test_view_directory(self, tmp_path):
        """view() can list directory contents."""
        # Create some test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("print('hello')")
        
        result = view(str(tmp_path))
        
        # Result should contain the filenames
        assert "file1.txt" in result
        assert "file2.py" in result

    def test_view_file(self, tmp_path):
        """view() can read file contents."""
        test_content = "line 1\nline 2\nline 3\n"
        test_file = tmp_path / "test.txt"
        test_file.write_text(test_content)
        
        result = view(str(test_file))
        
        # Result should contain the file content
        assert "line 1" in result
        assert "line 2" in result
        assert "line 3" in result

    def test_view_file_with_line_range(self, tmp_path):
        """view() can read specific line ranges."""
        lines = "\n".join(f"line {i}" for i in range(1, 11))
        test_file = tmp_path / "test.txt"
        test_file.write_text(lines)
        
        result = view(str(test_file), view_range=(3, 5))
        
        # Should only contain lines 3-5
        assert "line 3" in result
        assert "line 4" in result
        assert "line 5" in result
        # Should not contain lines outside range
        assert "line 1" not in result
        assert "line 2" not in result
        assert "line 6" not in result

    def test_view_nonexistent_file(self):
        """view() returns error for nonexistent files."""
        result = view("/nonexistent/path/to/file.txt")
        
        assert "Error" in result or "not found" in result.lower()

    def test_create_new_file(self, tmp_path):
        """create() can create a new file."""
        new_file = tmp_path / "new_file.txt"
        content = "Hello, World!"
        
        result = create(str(new_file), content)
        
        # File should exist with correct content
        assert new_file.exists()
        assert new_file.read_text() == content
        assert "Created" in result or "created" in result.lower()

    def test_create_refuses_overwrite_by_default(self, tmp_path):
        """create() refuses to overwrite existing files by default."""
        existing_file = tmp_path / "existing.txt"
        existing_file.write_text("original content")
        
        result = create(str(existing_file), "new content")
        
        # Should not overwrite
        assert existing_file.read_text() == "original content"
        assert "Error" in result or "exists" in result.lower()

    def test_create_with_overwrite(self, tmp_path):
        """create() can overwrite when explicitly allowed."""
        existing_file = tmp_path / "existing.txt"
        existing_file.write_text("original content")
        
        result = create(str(existing_file), "new content", overwrite=True)
        
        # Should overwrite
        assert existing_file.read_text() == "new content"

    def test_str_replace_single_match(self, tmp_path):
        """str_replace() replaces text when there's exactly one match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        
        result = str_replace(str(test_file), "World", "Universe")
        
        assert test_file.read_text() == "Hello, Universe!"
        assert "Replaced" in result or "replaced" in result.lower()

    def test_str_replace_no_match(self, tmp_path):
        """str_replace() returns error when text not found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        
        result = str_replace(str(test_file), "Nonexistent", "Something")
        
        # Should not modify file
        assert test_file.read_text() == "Hello, World!"
        assert "Error" in result or "not found" in result.lower()

    def test_str_replace_multiple_matches(self, tmp_path):
        """str_replace() returns error when multiple matches found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello Hello Hello")
        
        result = str_replace(str(test_file), "Hello", "Hi")
        
        # Should not modify file due to ambiguity
        assert test_file.read_text() == "Hello Hello Hello"
        assert "Error" in result or "multiple" in result.lower()

    def test_insert_at_line(self, tmp_path):
        """insert() can insert text at a specific line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 0\nline 1\nline 2")
        
        result = insert(str(test_file), 1, "inserted line")
        
        content = test_file.read_text()
        lines = content.split("\n")
        assert lines[1] == "inserted line"
        assert "Inserted" in result or "inserted" in result.lower()


class TestParserWithFastcoreToolNames:
    """Test that parser correctly handles fastcore.tools function names."""

    def test_parse_view_reference(self):
        """Parser extracts &view correctly."""
        import re
        prompt = "Use &view to explore the directory"
        pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
        
        matches = re.findall(pattern, prompt)
        
        assert matches == ["view"]

    def test_parse_multiple_fastcore_tools(self):
        """Parser extracts multiple fastcore.tools references."""
        import re
        prompt = "Use &view to see files, &rg to search, and &create to make new files"
        pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
        
        matches = re.findall(pattern, prompt)
        
        assert "view" in matches
        assert "rg" in matches
        assert "create" in matches
        assert len(matches) == 3

    def test_parse_str_replace_with_underscore(self):
        """Parser handles underscores in &str_replace correctly."""
        import re
        prompt = "Use &str_replace to fix the typo"
        pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
        
        matches = re.findall(pattern, prompt)
        
        assert matches == ["str_replace"]

    def test_removal_of_tool_references(self):
        """Function references are properly removed from prompts."""
        import re
        prompt = "Use &view to explore and &rg to search the code"
        pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
        
        result = re.sub(pattern, '', prompt)
        result = ' '.join(result.split())
        
        assert "&" not in result
        assert "view" not in result
        assert "rg" not in result
        # But natural words remain
        assert "explore" in result
        assert "search" in result


class TestEndToEndToolFlow:
    """Test the complete flow from prompt to tool execution."""

    def _simulate_tool_call(self, func, args_dict):
        """Simulate how ai-jup would call a tool."""
        return func(**args_dict)

    def test_view_tool_call_simulation(self, tmp_path):
        """Simulate AI calling view() with JSON-like args."""
        # Create a test file
        test_file = tmp_path / "code.py"
        test_file.write_text("def hello():\n    print('world')")
        
        # This is how the AI would specify args
        tool_args = {"path": str(test_file)}
        
        result = self._simulate_tool_call(view, tool_args)
        
        assert "def hello" in result
        assert "print" in result

    def test_create_tool_call_simulation(self, tmp_path):
        """Simulate AI calling create() with JSON-like args."""
        new_file = tmp_path / "generated.py"
        
        tool_args = {
            "path": str(new_file),
            "file_text": "# Generated by AI\nprint('hello')"
        }
        
        result = self._simulate_tool_call(create, tool_args)
        
        assert new_file.exists()
        content = new_file.read_text()
        assert "Generated by AI" in content

    def test_str_replace_tool_call_simulation(self, tmp_path):
        """Simulate AI calling str_replace() with JSON-like args."""
        test_file = tmp_path / "config.txt"
        test_file.write_text("debug = False")
        
        tool_args = {
            "path": str(test_file),
            "old_str": "debug = False",
            "new_str": "debug = True"
        }
        
        result = self._simulate_tool_call(str_replace, tool_args)
        
        assert test_file.read_text() == "debug = True"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
