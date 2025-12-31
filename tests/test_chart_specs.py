"""Tests for chart specification support in prompts (Tier 2 multimodal)."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _blocks_to_text(blocks: list) -> str:
    """Helper to convert system prompt blocks to text for assertions (text blocks only)."""
    return " ".join(block.get("text", "") for block in blocks if block.get("type") == "text")


def test_build_system_prompt_with_vegalite_spec():
    """Test system prompt building with Vega-Lite (Altair) chart spec."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    chart_specs = [
        {
            "type": "vega-lite",
            "spec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "data": {"values": [{"x": 1, "y": 2}]},
                "mark": "bar",
                "encoding": {
                    "x": {"field": "x", "type": "quantitative"},
                    "y": {"field": "y", "type": "quantitative"}
                }
            },
            "cellIndex": 0
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, [], chart_specs)
    text = _blocks_to_text(blocks)
    
    # Should mention chart specs in base instructions
    assert "1 chart specification(s)" in text
    assert "Vega-Lite" in text or "vega-lite" in text.lower()
    print("✓ System prompt mentions Vega-Lite chart specs")
    
    # Should contain the JSON spec
    assert '"mark": "bar"' in text
    assert '"$schema"' in text
    print("✓ Vega-Lite spec JSON included in system prompt")


def test_build_system_prompt_with_plotly_spec():
    """Test system prompt building with Plotly chart spec."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    chart_specs = [
        {
            "type": "plotly",
            "spec": {
                "data": [{"x": [1, 2, 3], "y": [4, 5, 6], "type": "scatter"}],
                "layout": {"title": "My Plotly Chart"}
            },
            "cellIndex": 1
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, [], chart_specs)
    text = _blocks_to_text(blocks)
    
    # Should mention Plotly
    assert "Plotly" in text
    print("✓ System prompt mentions Plotly")
    
    # Should contain the spec content
    assert '"type": "scatter"' in text
    assert '"title": "My Plotly Chart"' in text
    print("✓ Plotly spec JSON included in system prompt")


def test_build_system_prompt_with_multiple_chart_specs():
    """Test system prompt with multiple chart specs from different libraries."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    chart_specs = [
        {
            "type": "vega-lite",
            "spec": {"mark": "bar", "data": {}},
            "cellIndex": 0
        },
        {
            "type": "plotly",
            "spec": {"data": [], "layout": {}},
            "cellIndex": 2
        },
        {
            "type": "vega-lite",
            "spec": {"mark": "point", "data": {}},
            "cellIndex": 3
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, [], chart_specs)
    text = _blocks_to_text(blocks)
    
    # Should mention 3 chart specs
    assert "3 chart specification(s)" in text
    print("✓ System prompt correctly counts multiple chart specs")
    
    # Should have sections for each chart
    assert "Chart Specification 1" in text
    assert "Chart Specification 2" in text
    assert "Chart Specification 3" in text
    print("✓ Each chart spec has its own section")
    
    # Should mention cell indices
    assert "cell 0" in text
    assert "cell 2" in text
    assert "cell 3" in text
    print("✓ Cell indices included in chart spec descriptions")


def test_build_system_prompt_with_both_images_and_charts():
    """Test system prompt with both images and chart specs."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    images = [
        {
            "data": "base64imagedata",
            "mimeType": "image/png",
            "source": "output",
            "cellIndex": 1
        }
    ]
    
    chart_specs = [
        {
            "type": "vega-lite",
            "spec": {"mark": "line"},
            "cellIndex": 2
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, images, chart_specs)
    text = _blocks_to_text(blocks)
    
    # Should mention both
    assert "1 image(s)" in text
    assert "1 chart specification(s)" in text
    print("✓ System prompt mentions both images and chart specs")
    
    # Should have image block
    image_blocks = [b for b in blocks if b.get("type") == "image"]
    assert len(image_blocks) == 1
    print("✓ Image block present")
    
    # Should have chart spec in text
    assert '"mark": "line"' in text
    print("✓ Chart spec present in text")


def test_build_system_prompt_no_chart_specs():
    """Test that system prompt works normally without chart specs."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    blocks = handler._build_system_prompt("import pandas", {"x": {"type": "int", "repr": "5"}}, {}, [], [])
    text = _blocks_to_text(blocks)
    
    # Should not mention chart specs
    assert "chart specification(s)" not in text
    
    # Should have normal content
    assert "import pandas" in text
    assert "Available Variables" in text
    print("✓ System prompt works without chart specs")


def test_build_system_prompt_chart_specs_none():
    """Test that system prompt handles None chart_specs parameter."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    # None chart_specs (backwards compatibility)
    blocks = handler._build_system_prompt("", {}, {}, None, None)
    
    # Should work without error
    assert isinstance(blocks, list)
    assert len(blocks) >= 1
    print("✓ System prompt handles None chart_specs gracefully")


def test_large_chart_spec_truncation():
    """Test that large chart specs are truncated to avoid token overflow."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    # Create a very large spec - put "mark" field first so it appears before data
    large_data = [{"x": i, "y": i * 2, "label": f"point_{i}"} for i in range(1000)]
    chart_specs = [
        {
            "type": "vega-lite",
            "spec": {
                "aaa_mark": "point",  # Ensure this comes first alphabetically
                "data": {"values": large_data}
            },
            "cellIndex": 0
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, [], chart_specs)
    text = _blocks_to_text(blocks)
    
    # Should be truncated
    assert "... (truncated)" in text
    print("✓ Large chart specs are truncated")
    
    # But should still have the beginning (field that comes first alphabetically)
    assert '"aaa_mark"' in text
    print("✓ Truncated spec still contains beginning of JSON")


def test_chart_spec_type_labels():
    """Test that chart type labels are formatted nicely."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    chart_specs = [
        {"type": "vega-lite", "spec": {}, "cellIndex": 0},
        {"type": "plotly", "spec": {}, "cellIndex": 1}
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, [], chart_specs)
    text = _blocks_to_text(blocks)
    
    # Vega-Lite should show as "Vega-Lite (Altair)"
    assert "Vega-Lite (Altair)" in text
    print("✓ Vega-Lite labeled as 'Vega-Lite (Altair)'")
    
    # Plotly should show as "Plotly"
    assert "Plotly" in text
    print("✓ Plotly labeled correctly")


if __name__ == "__main__":
    test_build_system_prompt_with_vegalite_spec()
    test_build_system_prompt_with_plotly_spec()
    test_build_system_prompt_with_multiple_chart_specs()
    test_build_system_prompt_with_both_images_and_charts()
    test_build_system_prompt_no_chart_specs()
    test_build_system_prompt_chart_specs_none()
    test_large_chart_spec_truncation()
    test_chart_spec_type_labels()
    print("\n✅ All chart spec tests passed!")
