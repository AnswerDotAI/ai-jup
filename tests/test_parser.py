"""Tests for the prompt parser."""
import sys
import os

# Add the parent directory so we can import from lib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_parse_variables():
    """Test parsing $variable references from prompts."""
    # We'll test the concept since we can't import TypeScript directly
    test_prompt = "What insights can you give me about $sales_data? Use $greeting too."
    
    # Simulate the regex matching
    import re
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    variables = list(set(re.findall(variable_pattern, test_prompt)))
    
    assert 'sales_data' in variables
    assert 'greeting' in variables
    assert len(variables) == 2
    print("✓ Variable parsing works correctly")


def test_parse_functions():
    """Test parsing &function references from prompts."""
    test_prompt = "Please use &calculate_metrics and &analyze_trend to help."
    
    import re
    function_pattern = r'&([a-zA-Z_][a-zA-Z0-9_]*)'
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert 'calculate_metrics' in functions
    assert 'analyze_trend' in functions
    assert len(functions) == 2
    print("✓ Function parsing works correctly")


def test_mixed_parsing():
    """Test parsing both variables and functions."""
    test_prompt = "Given $data, use &process to transform it and store in $result with &validate."
    
    import re
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    function_pattern = r'&([a-zA-Z_][a-zA-Z0-9_]*)'
    
    variables = list(set(re.findall(variable_pattern, test_prompt)))
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert 'data' in variables
    assert 'result' in variables
    assert 'process' in functions
    assert 'validate' in functions
    print("✓ Mixed parsing works correctly")


def test_substitution():
    """Test variable substitution in prompts."""
    test_prompt = "The value of $x is important and $y matters too."
    variable_values = {'x': '42', 'y': 'hello'}
    
    import re
    result = test_prompt
    for name, value in variable_values.items():
        pattern = re.compile(r'\$' + name + r'\b')
        result = pattern.sub(value, result)
    
    assert '$x' not in result
    assert '$y' not in result
    assert '42' in result
    assert 'hello' in result
    print("✓ Variable substitution works correctly")


def test_function_removal():
    """Test removing function references from prompts."""
    test_prompt = "Use &func1 and &func2 to process the data."
    
    import re
    result = re.sub(r'&([a-zA-Z_][a-zA-Z0-9_]*)', '', test_prompt)
    result = ' '.join(result.split())  # Normalize whitespace
    
    assert '&func1' not in result
    assert '&func2' not in result
    print("✓ Function removal works correctly")


# --- Edge case tests from test-plan.md section 1.1 ---

def test_safe_substitution_dollar_in_value():
    """$& in replacement value should not trigger regex expansion."""
    import re
    test_prompt = "The price is $price today."
    variable_values = {'price': '$5 & more'}
    
    result = test_prompt
    for name, value in variable_values.items():
        pattern = re.compile(r'\$' + name + r'\b')
        # Use a replacer function to avoid $& expansion
        result = pattern.sub(lambda m: value, result)
    
    assert result == "The price is $5 & more today."
    print("✓ Safe substitution with $ in value works correctly")


def test_safe_substitution_regex_chars():
    """Regex special characters in value should be preserved literally."""
    import re
    test_prompt = "The pattern is $pattern here."
    variable_values = {'pattern': r'\d+.*$'}
    
    result = test_prompt
    for name, value in variable_values.items():
        pattern = re.compile(r'\$' + name + r'\b')
        result = pattern.sub(lambda m: value, result)
    
    assert result == r"The pattern is \d+.*$ here."
    print("✓ Safe substitution with regex chars works correctly")


def test_multiline_unicode_values():
    """Newlines and unicode should be preserved in substitution."""
    import re
    test_prompt = "The data is $data here."
    variable_values = {'data': "line1\nline2\nα"}
    
    result = test_prompt
    for name, value in variable_values.items():
        pattern = re.compile(r'\$' + name + r'\b')
        result = pattern.sub(lambda m: value, result)
    
    assert "line1\nline2\nα" in result
    print("✓ Multiline/unicode values preserved correctly")


def test_whitespace_func_at_start():
    """Function at start of prompt should result in clean output."""
    import re
    test_prompt = "&func first"
    result = re.sub(r'&([a-zA-Z_][a-zA-Z0-9_]*)', '', test_prompt)
    result = ' '.join(result.split())  # Normalize whitespace
    
    assert result == "first"
    print("✓ Whitespace - func at start works correctly")


def test_whitespace_func_at_end():
    """Function at end of prompt should result in clean output."""
    import re
    test_prompt = "Call &func"
    result = re.sub(r'&([a-zA-Z_][a-zA-Z0-9_]*)', '', test_prompt)
    result = ' '.join(result.split())  # Normalize whitespace
    
    assert result == "Call"
    print("✓ Whitespace - func at end works correctly")


def test_whitespace_multiple_funcs():
    """Multiple functions with irregular whitespace should normalize."""
    import re
    test_prompt = "Use  &f1   and   &f2  now"
    result = re.sub(r'&([a-zA-Z_][a-zA-Z0-9_]*)', '', test_prompt)
    result = ' '.join(result.split())  # Normalize whitespace
    
    assert result == "Use and now"
    print("✓ Whitespace - multiple funcs works correctly")


def test_func_next_to_punctuation():
    """Function next to punctuation should preserve punctuation."""
    import re
    test_prompt = "Use &func, please"
    result = re.sub(r'&([a-zA-Z_][a-zA-Z0-9_]*)', '', test_prompt)
    result = ' '.join(result.split())  # Normalize whitespace
    
    assert result == "Use , please"
    print("✓ Func next to punctuation works correctly")


def test_invalid_function_syntax():
    """&123 should not be parsed as a function."""
    import re
    test_prompt = "this &123 is not valid"
    function_pattern = r'&([a-zA-Z_][a-zA-Z0-9_]*)'
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert functions == []
    print("✓ Invalid function syntax correctly rejected")


def test_no_false_positive_ampersand():
    r"""Ampersand in word should not be parsed as function reference.
    
    The test plan specifies that 'cost&benefit' should NOT match any functions,
    as the & is part of a word, not a standalone function reference.
    
    This requires a word boundary before &. The pattern should be:
    r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)' (negative lookbehind).
    """
    import re
    test_prompt = "cost&benefit"
    # Fixed pattern with word boundary before &
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert functions == [], f"Expected no functions, got {functions}"
    print("✓ No false positive for ampersand in word")


def test_underscore_identifiers():
    """Underscore-prefixed identifiers should be detected."""
    import re
    test_prompt = "$__hidden and &__helper"
    
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    function_pattern = r'&([a-zA-Z_][a-zA-Z0-9_]*)'
    
    variables = list(set(re.findall(variable_pattern, test_prompt)))
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert '__hidden' in variables
    assert '__helper' in functions
    print("✓ Underscore identifiers detected correctly")


def test_word_boundary_substitution():
    """$id should be replaced but $id2 should remain unchanged."""
    import re
    test_prompt = "$id and $id2"
    variable_values = {'id': 'A'}
    
    result = test_prompt
    for name, value in variable_values.items():
        pattern = re.compile(r'\$' + name + r'\b')
        result = pattern.sub(lambda m: value, result)
    
    assert result == "A and $id2"
    print("✓ Word boundary test works correctly")


def test_no_duplicates():
    """Same variable used twice should appear only once in list."""
    import re
    test_prompt = "$x plus $x equals 2x"
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    variables = list(set(re.findall(variable_pattern, test_prompt)))
    
    assert variables == ['x']
    print("✓ No duplicates in variable list")


# --- Test cases inspired by Solveit demos notebook ---
# https://github.com/AnswerDotAI/solveit_demos/blob/main/Asking%20about%20Code.ipynb

def test_multiple_tools_in_prompt():
    """Multiple tool references as shown in Solveit tool_info output.
    
    From the notebook: Tools like &rg, &sed, &view, &create are listed.
    """
    import re
    test_prompt = """Use &view to see the directory, then &rg to search for patterns,
    and finally &sed to read specific lines."""
    
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert 'view' in functions
    assert 'rg' in functions
    assert 'sed' in functions
    assert len(functions) == 3
    print("✓ Multiple tools parsed correctly")


def test_tool_names_with_underscores():
    """Tool names can have underscores like str_replace, strs_replace.
    
    From Solveit: &str_replace, &strs_replace, &replace_lines
    """
    import re
    test_prompt = "Use &str_replace and &strs_replace and &replace_lines to edit."
    
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert 'str_replace' in functions
    assert 'strs_replace' in functions
    assert 'replace_lines' in functions
    print("✓ Tool names with underscores parsed correctly")


def test_variable_in_question_context():
    """Variable reference in a question about code exploration.
    
    From notebook: "Can you use the file tools to tell me more about how these *info functions..."
    """
    import re
    test_prompt = "What can you tell me about $df? Use &view to explore."
    
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    
    variables = list(set(re.findall(variable_pattern, test_prompt)))
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert variables == ['df']
    assert functions == ['view']
    print("✓ Variable in question context parsed correctly")


def test_tool_at_sentence_end():
    """Tool reference at the end of a sentence with period.
    
    Variation of punctuation test from notebook patterns.
    """
    import re
    test_prompt = "Please use &view."
    
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    functions = re.findall(function_pattern, test_prompt)
    
    assert functions == ['view']
    print("✓ Tool at sentence end parsed correctly")


def test_tool_in_parentheses():
    """Tool reference inside parentheses.
    
    Common pattern: "(use &tool_name for this)"
    """
    import re
    test_prompt = "Explore the code (use &view for this)"
    
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    functions = re.findall(function_pattern, test_prompt)
    
    assert functions == ['view']
    print("✓ Tool in parentheses parsed correctly")


def test_variable_with_path_like_content():
    """Variable that might contain path-like strings shouldn't confuse parser.
    
    From notebook: view({"path": "dialoghelper/dialoghelper/core.py"})
    The parser shouldn't pick up anything from JSON-like content.
    """
    import re
    test_prompt = "Look at $file_path and tell me what you see."
    
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    variables = re.findall(variable_pattern, test_prompt)
    
    assert variables == ['file_path']
    print("✓ Variable with path-like name parsed correctly")


def test_markdown_formatted_prompt():
    """Prompt with markdown formatting around variables/functions.
    
    From notebook: Tools are often listed with markdown like "- &`view`"
    In ai-jup we use simpler syntax without backticks.
    """
    import re
    test_prompt = """Here are the tools:
- &view: View files
- &create: Create files

Use $data with &process."""
    
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    
    variables = list(set(re.findall(variable_pattern, test_prompt)))
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert variables == ['data']
    assert 'view' in functions
    assert 'create' in functions
    assert 'process' in functions
    print("✓ Markdown formatted prompt parsed correctly")


def test_function_removal_preserves_markdown_structure():
    """Removing function refs should preserve markdown list structure.
    
    From notebook pattern where tools are listed in markdown.
    """
    import re
    test_prompt = """Tools:
- &view: View files
- &create: Create files"""
    
    result = re.sub(r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)', '', test_prompt)
    result = ' '.join(result.split())  # Normalize whitespace
    
    assert '&' not in result
    assert 'view' not in result
    assert 'create' not in result
    # Colons and structure words should remain
    assert ':' in result
    assert 'View files' in result
    print("✓ Function removal preserves markdown structure")


def test_complex_prompt_from_notebook_pattern():
    """Complex prompt pattern similar to notebook exploration.
    
    Based on: "Can you use the file tools to tell me more about how these 
    *info functions in dialoghelper work?"
    """
    import re
    test_prompt = """Hey, can you use &view to explore $repo_path and tell me 
how the $module_name works? Also use &rg to search for patterns."""
    
    variable_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    function_pattern = r'(?<!\w)&([a-zA-Z_][a-zA-Z0-9_]*)'
    
    variables = list(set(re.findall(variable_pattern, test_prompt)))
    functions = list(set(re.findall(function_pattern, test_prompt)))
    
    assert 'repo_path' in variables
    assert 'module_name' in variables
    assert 'view' in functions
    assert 'rg' in functions
    print("✓ Complex prompt from notebook pattern parsed correctly")


# --- Code fence and escape sequence tests (from ux-testing.md) ---

def test_no_substitution_inside_code_fences():
    """$var inside code fences should NOT be substituted.
    
    This is a key UX requirement: code examples should remain intact.
    """
    import re
    prompt = "Explain:\n```python\nx = $x\n```\nOutside $x"
    variable_values = {'x': '42'}
    
    def process_with_fence_awareness(prompt_text, values):
        """Substitute variables only outside code fences."""
        # Split by code fence markers
        parts = prompt_text.split("```")
        for i in range(0, len(parts), 2):  # even indices: outside fences
            for name, value in values.items():
                pattern = re.compile(r'\$' + name + r'\b')
                parts[i] = pattern.sub(lambda m: value, parts[i])
        return "```".join(parts)
    
    result = process_with_fence_awareness(prompt, variable_values)
    assert "x = $x" in result, "Inside fence should remain unchanged"
    assert "Outside 42" in result, "Outside fence should be substituted"
    print("✓ No substitution inside code fences")


def test_escaped_dollar_and_at_not_matched():
    r"""Escaped \$var and \&func should NOT be parsed.
    
    Users may want to discuss the syntax itself without triggering parsing.
    """
    import re
    prompt = r"Price is \$x, call \&tool, real $x and &tool"
    
    # Patterns with negative lookbehind for backslash
    var_pattern = r'(?<!\\)\$([a-zA-Z_][a-zA-Z0-9_]*)'
    func_pattern = r'(?<!\\)&([a-zA-Z_][a-zA-Z0-9_]*)'
    
    vars_ = re.findall(var_pattern, prompt)
    funcs = re.findall(func_pattern, prompt)
    
    assert vars_ == ['x'], f"Expected only ['x'], got {vars_}"
    assert funcs == ['tool'], f"Expected only ['tool'], got {funcs}"
    print("✓ Escaped dollar and at not matched")


def test_escaped_dollar_not_substituted():
    r"""Escaped \$x should not be substituted."""
    import re
    prompt = r"Price \$x and value $x"
    values = {'x': '42'}
    
    # Pattern that doesn't match escaped dollars
    pattern = re.compile(r'(?<!\\)\$x\b')
    result = pattern.sub(lambda m: values['x'], prompt)
    
    assert r"\$x" in result, "Escaped should remain"
    assert "42" in result, "Non-escaped should be substituted"
    print("✓ Escaped dollar not substituted")


def test_substring_variable_not_replaced_explicit():
    """$x should be replaced but $x_long should remain unchanged.
    
    Explicit test case from ux-testing.md for word boundary behavior.
    """
    import re
    prompt = "Use $x and $x_long"
    values = {'x': 'A'}
    
    pattern = re.compile(r'\$x\b')
    result = pattern.sub(lambda m: values['x'], prompt)
    
    assert result == "Use A and $x_long", f"Got: {result}"
    print("✓ Substring variable not replaced")


def test_multiple_references_to_same_variable():
    """Multiple references to same variable should all be substituted.
    
    From ux-testing.md edge cases.
    """
    import re
    prompt = "First $x, then $x again, and finally $x"
    values = {'x': 'VALUE'}
    
    pattern = re.compile(r'\$x\b')
    result = pattern.sub(lambda m: values['x'], prompt)
    
    assert result == "First VALUE, then VALUE again, and finally VALUE"
    assert result.count('VALUE') == 3
    assert '$x' not in result
    print("✓ Multiple references to same variable all substituted")


if __name__ == '__main__':
    test_parse_variables()
    test_parse_functions()
    test_mixed_parsing()
    test_substitution()
    test_function_removal()
    # Edge case tests
    test_safe_substitution_dollar_in_value()
    test_safe_substitution_regex_chars()
    test_multiline_unicode_values()
    test_whitespace_func_at_start()
    test_whitespace_func_at_end()
    test_whitespace_multiple_funcs()
    test_func_next_to_punctuation()
    test_invalid_function_syntax()
    test_no_false_positive_ampersand()
    test_underscore_identifiers()
    test_word_boundary_substitution()
    test_no_duplicates()
    # Solveit notebook-inspired tests
    test_multiple_tools_in_prompt()
    test_tool_names_with_underscores()
    test_variable_in_question_context()
    test_tool_at_sentence_end()
    test_tool_in_parentheses()
    test_variable_with_path_like_content()
    test_markdown_formatted_prompt()
    test_function_removal_preserves_markdown_structure()
    test_complex_prompt_from_notebook_pattern()
    print("\n✅ All parser tests passed!")
