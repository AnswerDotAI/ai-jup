"""Tests for multimodal image support in prompts."""
import json
import sys
import os
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _blocks_to_text(blocks: list) -> str:
    """Helper to convert system prompt blocks to text for assertions (text blocks only)."""
    return " ".join(block.get("text", "") for block in blocks if block.get("type") == "text")


def _get_image_blocks(blocks: list) -> list:
    """Extract image blocks from system prompt blocks."""
    return [block for block in blocks if block.get("type") == "image"]


def test_build_system_prompt_with_images():
    """Test system prompt building with image context."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    # Create test images
    images = [
        {
            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
            "mimeType": "image/png",
            "source": "output",
            "cellIndex": 0
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, images)
    
    # Should contain mention of images in base instructions
    text = _blocks_to_text(blocks)
    assert "1 image(s)" in text
    assert "outputs from" in text.lower() or "cell output" in text.lower()
    print("✓ System prompt mentions images when present")
    
    # Should contain image blocks
    image_blocks = _get_image_blocks(blocks)
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["type"] == "base64"
    assert image_blocks[0]["source"]["media_type"] == "image/png"
    assert image_blocks[0]["source"]["data"] == images[0]["data"]
    print("✓ Image block correctly formatted for Anthropic API")


def test_build_system_prompt_with_multiple_images():
    """Test system prompt with multiple images from different sources."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    images = [
        {
            "data": "png_data_1",
            "mimeType": "image/png",
            "source": "output",
            "cellIndex": 0
        },
        {
            "data": "jpeg_data",
            "mimeType": "image/jpeg",
            "source": "attachment",
            "cellIndex": 1
        },
        {
            "data": "png_data_2",
            "mimeType": "image/png",
            "source": "output",
            "cellIndex": 2
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, images)
    
    # Should mention 3 images
    text = _blocks_to_text(blocks)
    assert "3 image(s)" in text
    print("✓ System prompt correctly counts multiple images")
    
    # Should have 3 image blocks
    image_blocks = _get_image_blocks(blocks)
    assert len(image_blocks) == 3
    
    # Check each image block
    assert image_blocks[0]["source"]["media_type"] == "image/png"
    assert image_blocks[0]["source"]["data"] == "png_data_1"
    
    assert image_blocks[1]["source"]["media_type"] == "image/jpeg"
    assert image_blocks[1]["source"]["data"] == "jpeg_data"
    
    assert image_blocks[2]["source"]["media_type"] == "image/png"
    assert image_blocks[2]["source"]["data"] == "png_data_2"
    print("✓ Multiple images correctly formatted")


def test_build_system_prompt_image_descriptions():
    """Test that image blocks have descriptions with source and cell info."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    images = [
        {
            "data": "output_image",
            "mimeType": "image/png",
            "source": "output",
            "cellIndex": 5
        },
        {
            "data": "attachment_image",
            "mimeType": "image/jpeg",
            "source": "attachment",
            "cellIndex": 3
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, images)
    text = _blocks_to_text(blocks)
    
    # Check for image descriptions
    assert "cell output" in text.lower()
    assert "cell 5" in text.lower()
    assert "markdown attachment" in text.lower() or "attachment" in text.lower()
    assert "cell 3" in text.lower()
    print("✓ Image descriptions include source type and cell index")


def test_build_system_prompt_no_images():
    """Test that system prompt works normally without images."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    # No images passed
    blocks = handler._build_system_prompt("import pandas", {"x": {"type": "int", "repr": "5"}}, {}, [])
    
    text = _blocks_to_text(blocks)
    
    # Should not mention images
    assert "image(s)" not in text.lower()
    
    # Should have normal content
    assert "import pandas" in text
    assert "Available Variables" in text
    print("✓ System prompt works without images")
    
    # Should have no image blocks
    image_blocks = _get_image_blocks(blocks)
    assert len(image_blocks) == 0
    print("✓ No image blocks when no images provided")


def test_build_system_prompt_images_with_none():
    """Test that system prompt handles None images parameter."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    # None images (backwards compatibility)
    blocks = handler._build_system_prompt("", {}, {}, None)
    
    # Should work without error
    assert isinstance(blocks, list)
    assert len(blocks) >= 1
    
    # Should have no image blocks
    image_blocks = _get_image_blocks(blocks)
    assert len(image_blocks) == 0
    print("✓ System prompt handles None images gracefully")


def test_image_block_structure():
    """Test the exact structure of image blocks for Anthropic API."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    # Test with a realistic base64 PNG (1x1 red pixel)
    red_pixel_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    
    images = [
        {
            "data": red_pixel_png,
            "mimeType": "image/png",
            "source": "output",
            "cellIndex": 0
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, images)
    image_blocks = _get_image_blocks(blocks)
    
    assert len(image_blocks) == 1
    img_block = image_blocks[0]
    
    # Verify exact structure for Anthropic API
    assert img_block["type"] == "image"
    assert "source" in img_block
    assert img_block["source"]["type"] == "base64"
    assert img_block["source"]["media_type"] == "image/png"
    assert img_block["source"]["data"] == red_pixel_png
    print("✓ Image block structure matches Anthropic API format")


def test_gif_image_support():
    """Test that GIF images are correctly handled."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    images = [
        {
            "data": "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
            "mimeType": "image/gif",
            "source": "output",
            "cellIndex": 0
        }
    ]
    
    blocks = handler._build_system_prompt("", {}, {}, images)
    image_blocks = _get_image_blocks(blocks)
    
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["media_type"] == "image/gif"
    print("✓ GIF images are correctly handled")


if __name__ == "__main__":
    test_build_system_prompt_with_images()
    test_build_system_prompt_with_multiple_images()
    test_build_system_prompt_image_descriptions()
    test_build_system_prompt_no_images()
    test_build_system_prompt_images_with_none()
    test_image_block_structure()
    test_gif_image_support()
    print("\n✅ All multimodal tests passed!")
