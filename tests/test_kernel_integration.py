"""Integration tests for kernel introspection functionality.

This tests the Python code that would be executed by the kernel connector
to introspect variables and functions.
"""


def test_variable_introspection():
    """Test that variable introspection code works correctly."""
    import json
    
    # Set up test environment
    test_var = [1, 2, 3, 4, 5]
    test_df = {"a": 1, "b": 2}  # Simulating a dict instead of DataFrame for simplicity
    test_str = "Hello, World!"
    
    # This is the code the kernel connector would run
    def get_variable_info(name, value):
        return {
            "name": name,
            "type": type(value).__name__,
            "repr": repr(value)[:500]
        }
    
    # Test list
    info = get_variable_info("test_var", test_var)
    assert info["name"] == "test_var"
    assert info["type"] == "list"
    assert "[1, 2, 3, 4, 5]" in info["repr"]
    
    # Test dict
    info = get_variable_info("test_df", test_df)
    assert info["type"] == "dict"
    
    # Test string
    info = get_variable_info("test_str", test_str)
    assert info["type"] == "str"
    
    print("✓ Variable introspection works correctly")


def test_function_introspection():
    """Test that function introspection code works correctly."""
    import inspect
    import json
    
    def sample_function(x: int, y: str = "default") -> str:
        """A sample function for testing.
        
        Args:
            x: An integer parameter
            y: A string parameter with default
            
        Returns:
            A formatted string
        """
        return f"{y}: {x}"
    
    # This is the code the kernel connector would run
    def get_function_info(func):
        sig = str(inspect.signature(func))
        doc = inspect.getdoc(func) or "No documentation"
        params = {}
        
        for pname, param in inspect.signature(func).parameters.items():
            pinfo = {"type": "string", "description": pname}
            if param.annotation != inspect.Parameter.empty:
                ann = param.annotation
                if hasattr(ann, '__name__'):
                    pinfo["type"] = ann.__name__
            if param.default != inspect.Parameter.empty:
                pinfo["default"] = repr(param.default)
            params[pname] = pinfo
        
        return {
            "signature": sig,
            "docstring": doc[:500],
            "parameters": params
        }
    
    info = get_function_info(sample_function)
    
    assert "(x: int, y: str = 'default') -> str" in info["signature"]
    assert "sample function" in info["docstring"]
    assert "x" in info["parameters"]
    assert "y" in info["parameters"]
    assert info["parameters"]["x"]["type"] == "int"
    assert info["parameters"]["y"]["type"] == "str"
    assert "'default'" in info["parameters"]["y"]["default"]
    
    print("✓ Function introspection works correctly")


def test_get_all_variables():
    """Test getting all variables from a namespace."""
    import json
    
    # Simulate a kernel namespace
    namespace = {
        'x': 5,
        'y': 'hello',
        'df': [1, 2, 3],
        '_private': 'hidden',
        'some_func': lambda: None,
        '__builtins__': {},
    }
    
    skip = {'__builtins__'}
    vars_list = []
    
    for name, val in namespace.items():
        if name.startswith('_') or name in skip:
            continue
        if callable(val) and not isinstance(val, type):
            continue
        try:
            vars_list.append({
                "name": name,
                "type": type(val).__name__,
                "repr": repr(val)[:200]
            })
        except Exception:
            pass
    
    var_names = [v["name"] for v in vars_list]
    assert 'x' in var_names
    assert 'y' in var_names
    assert 'df' in var_names
    assert '_private' not in var_names
    assert 'some_func' not in var_names  # Functions are excluded
    
    print("✓ Get all variables works correctly")


def test_get_all_functions():
    """Test getting all callable functions from a namespace."""
    
    def func1():
        pass
    
    def func2(x):
        return x * 2
    
    class SomeClass:
        pass
    
    namespace = {
        'func1': func1,
        'func2': func2,
        'SomeClass': SomeClass,
        '_private_func': lambda: None,
        'x': 5,
    }
    
    funcs = []
    for name, val in namespace.items():
        if name.startswith('_'):
            continue
        if callable(val) and not isinstance(val, type):
            funcs.append(name)
    
    assert 'func1' in funcs
    assert 'func2' in funcs
    assert 'SomeClass' not in funcs  # Classes are excluded
    assert 'x' not in funcs
    assert '_private_func' not in funcs
    
    print("✓ Get all functions works correctly")


def test_function_call():
    """Test calling a function with arguments."""
    import json
    
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    
    # Simulate calling the function
    args = {"a": 5, "b": 3}
    result = add(**args)
    
    assert result == 8
    
    output = json.dumps({"result": repr(result)})
    parsed = json.loads(output)
    assert parsed["result"] == "8"
    
    print("✓ Function call works correctly")


if __name__ == '__main__':
    test_variable_introspection()
    test_function_introspection()
    test_get_all_variables()
    test_get_all_functions()
    test_function_call()
    print("\n✅ All kernel integration tests passed!")
