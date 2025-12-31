"""Server handlers for AI prompt processing."""
import json
import os
import re

from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
from tornado.web import authenticated
from tornado.iostream import StreamClosedError

# Regex for validating tool names (Python identifiers)
TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


def _validate_tool_args(tool_args):
    """Validate tool args as a kwargs-compatible dict."""
    if tool_args is None:
        return {}
    if not isinstance(tool_args, dict):
        raise ValueError("Tool input must be a JSON object")
    for key in tool_args.keys():
        if not isinstance(key, str) or not TOOL_NAME_RE.match(key):
            raise ValueError(f"Invalid tool argument name: {key}")
    return tool_args


def _build_tool_execution_code(tool_name: str, tool_args: dict, timeout: int) -> str:
    """Build Python code to execute a named function with JSON args safely.

    Tool args are passed as a JSON string and decoded in Python to avoid
    interpolating untrusted keys/values into executable code.
    """
    validated_args = _validate_tool_args(tool_args)
    args_json_literal = repr(json.dumps(validated_args))

    # Timeout protection uses signal (Unix) with graceful fallback.
    return f"""
import json as _json_mod
import base64 as _b64
import signal as _signal_mod

def _timeout_handler(*args):
    raise TimeoutError("Tool execution timed out after {timeout} seconds")

try:
    # Set up timeout (Unix only, gracefully ignored on Windows)
    try:
        _signal_mod.signal(_signal_mod.SIGALRM, _timeout_handler)
        _signal_mod.alarm({timeout})
    except (AttributeError, ValueError):
        pass  # Windows or unsupported platform
    
    _fn_name = {json.dumps(tool_name)}
    _fn = globals().get(_fn_name)
    if _fn is None or not callable(_fn):
        raise NameError(f"Tool '{{_fn_name}}' not found or not callable")
    
    _args = _json_mod.loads({args_json_literal})
    if not isinstance(_args, dict):
        raise TypeError("Tool input must decode to an object")
    
    _result = _fn(**_args)
    
    # Rich result handling
    try:
        # Check savefig FIRST - matplotlib Figures have _repr_html_ that returns None
        if hasattr(_result, 'savefig'):
            import io as _io
            _buf = _io.BytesIO()
            _result.savefig(_buf, format='png', bbox_inches='tight')
            _buf.seek(0)
            _content = {{"type": "image", "format": "png", "content": _b64.b64encode(_buf.getvalue()).decode("ascii")}}
        elif hasattr(_result, '_repr_png_'):
            _png_data = _result._repr_png_()
            if _png_data:
                _content = {{"type": "image", "format": "png", "content": _b64.b64encode(_png_data).decode("ascii")}}
            else:
                _content = {{"type": "text", "content": repr(_result)[:500]}}
        elif hasattr(_result, '_repr_html_'):
            _html = _result._repr_html_()
            if _html:
                _content = {{"type": "html", "content": _html[:10000]}}
            else:
                _content = {{"type": "text", "content": repr(_result)[:500]}}
        else:
            _content = {{"type": "text", "content": repr(_result)[:500]}}
    except Exception as _conv_e:
        _content = {{"type": "text", "content": "Error: " + str(_conv_e) + " | " + repr(_result)[:500]}}
    
    print(_json_mod.dumps({{"result": _content, "status": "success"}}))
except TimeoutError as _te:
    print(_json_mod.dumps({{"error": str(_te), "status": "error"}}))
except Exception as _e:
    print(_json_mod.dumps({{"error": str(_e), "status": "error"}}))
finally:
    try:
        _signal_mod.alarm(0)  # Cancel the alarm
    except (AttributeError, ValueError, NameError):
        pass
"""


class PromptHandler(APIHandler):
    """Handler for AI prompt requests with streaming support."""

    @authenticated
    async def post(self):
        """Process a prompt and stream the response with optional tool loop."""
        try:
            data = self.get_json_body() or {}
            if not isinstance(data, dict):
                self.set_status(400)
                self.finish({"error": "Invalid JSON body"})
                return
            prompt = data.get("prompt", "")
            context = data.get("context", {})
            variables = context.get("variables", {})
            functions = context.get("functions", {})
            preceding_code = context.get("preceding_code", "")
            images = context.get("images", [])  # Multimodal image context
            chart_specs = context.get("chartSpecs", [])  # Declarative viz specs
            model = data.get("model", "claude-sonnet-4-20250514")
            kernel_id = data.get("kernel_id")  # For server-side tool execution
            max_steps = int(data.get("max_steps", 1))  # Max tool loop iterations

            system_prompt = self._build_system_prompt(preceding_code, variables, functions, images, chart_specs)
            
            self.set_header("Content-Type", "text/event-stream")
            self.set_header("Cache-Control", "no-cache")
            self.set_header("Connection", "keep-alive")

            if not HAS_ANTHROPIC:
                self.set_status(500)
                self.finish({"error": "anthropic package not installed"})
                return

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                self.set_status(500)
                self.finish({"error": "ANTHROPIC_API_KEY environment variable not set"})
                return

            client = anthropic.AsyncAnthropic(api_key=api_key)
            
            tools = self._build_tools(functions)
            
            # Get kernel for tool execution if max_steps >= 1
            kernel = None
            if max_steps >= 1 and kernel_id:
                kernel_manager = self.settings.get("kernel_manager")
                if kernel_manager:
                    kernel = kernel_manager.get_kernel(kernel_id)
            
            messages = [{"role": "user", "content": prompt}]
            steps = 0
            
            while True:
                current_tool_call = None
                current_text_block = None
                tool_input_buffer = ""
                text_buffer = ""
                assistant_content = []
                
                async with client.messages.stream(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    tools=tools if tools else anthropic.NOT_GIVEN,
                ) as stream:
                    async for event in stream:
                        if hasattr(event, 'type'):
                            if event.type == 'content_block_delta':
                                # Handle both text and tool input deltas
                                if hasattr(event.delta, 'text'):
                                    text_buffer += event.delta.text
                                    await self._write_sse({"text": event.delta.text})
                                if hasattr(event.delta, 'partial_json') and current_tool_call:
                                    tool_input_buffer += event.delta.partial_json
                                    await self._write_sse({"tool_input": event.delta.partial_json})
                            elif event.type == 'content_block_start':
                                if hasattr(event.content_block, 'type'):
                                    if event.content_block.type == 'tool_use':
                                        current_tool_call = {
                                            "id": event.content_block.id,
                                            "name": event.content_block.name
                                        }
                                        tool_input_buffer = ""
                                        await self._write_sse({
                                            "tool_call": {
                                                "name": event.content_block.name,
                                                "id": event.content_block.id
                                            }
                                        })
                                    elif event.content_block.type == 'text':
                                        current_text_block = True
                                        text_buffer = ""
                            elif event.type == 'content_block_stop':
                                # Capture completed content blocks for message history
                                if current_tool_call:
                                    try:
                                        tool_args = json.loads(tool_input_buffer or "{}")
                                    except json.JSONDecodeError:
                                        tool_args = {"__invalid_json__": True, "__raw__": tool_input_buffer}
                                    assistant_content.append({
                                        "type": "tool_use",
                                        "id": current_tool_call["id"],
                                        "name": current_tool_call["name"],
                                        "input": tool_args
                                    })
                                    current_tool_call = None
                                    tool_input_buffer = ""
                                elif current_text_block and text_buffer:
                                    assistant_content.append({
                                        "type": "text",
                                        "text": text_buffer
                                    })
                                    current_text_block = None
                                    text_buffer = ""
                            elif event.type == 'message_stop':
                                pass  # Handled after stream closes
                
                # Find tool use blocks in assistant_content
                tool_use_blocks = [b for b in assistant_content if b.get("type") == "tool_use"]
                
                # Check if we should execute tools and loop
                if not tool_use_blocks or steps >= max_steps or not kernel:
                    await self._write_sse({"done": True})
                    break
                
                # Execute ALL tool use blocks and collect results
                tool_results = []
                should_break = False
                
                for tool_block in tool_use_blocks:
                    tool_name = tool_block["name"]
                    tool_args = tool_block["input"]
                    tool_id = tool_block["id"]
                    
                    # Check for invalid JSON that was marked during parsing
                    if isinstance(tool_args, dict) and tool_args.get("__invalid_json__"):
                        await self._write_sse({"error": f"Invalid tool input JSON for {tool_name}"})
                        should_break = True
                        break

                    # Validate tool argument names (kwargs-compatible; prevents code injection via keys)
                    try:
                        tool_args = _validate_tool_args(tool_args)
                    except ValueError as ve:
                        await self._write_sse({"error": str(ve)})
                        should_break = True
                        break
                    
                    # Validate tool name format (must be a valid Python identifier)
                    if not TOOL_NAME_RE.match(tool_name):
                        await self._write_sse({"error": f"Invalid tool name: {tool_name}"})
                        should_break = True
                        break
                    
                    # Validate tool name against registered functions
                    if tool_name not in functions:
                        await self._write_sse({"error": f"Unknown tool: {tool_name}"})
                        should_break = True
                        break
                    
                    # Execute tool in kernel
                    tool_result = await self._execute_tool_in_kernel(kernel, tool_name, tool_args)
                    
                    # Stream tool result to frontend
                    await self._write_sse({
                        "tool_result": {
                            "id": tool_id,
                            "name": tool_name,
                            "result": tool_result
                        }
                    })
                    
                    # Format result content for LLM context
                    if tool_result.get("status") == "error":
                        result_text = f"Error: {tool_result.get('error', 'Unknown error')}"
                    else:
                        result_content = tool_result.get("result", {})
                        if isinstance(result_content, dict):
                            if result_content.get("type") == "text":
                                result_text = result_content.get("content", "")
                            elif result_content.get("type") == "html":
                                result_text = f"[HTML output: {len(result_content.get('content', ''))} chars]"
                            elif result_content.get("type") == "image":
                                result_text = "[Image output]"
                            else:
                                result_text = json.dumps(result_content)
                        else:
                            result_text = str(result_content)
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_text
                    })
                
                if should_break:
                    await self._write_sse({"done": True})
                    break
                
                # Build messages for next LLM call
                # Add assistant message with ALL tool uses
                messages.append({
                    "role": "assistant",
                    "content": assistant_content
                })
                
                # Add ALL tool results in a single user message
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
                
                steps += 1

            self.finish()

        except StreamClosedError:
            # Client disconnected; nothing to do
            pass
        except Exception as e:
            self.log.error(f"Error processing prompt: {e}")
            try:
                await self._write_sse({"error": str(e)})
            except (Exception, StreamClosedError):
                pass
            try:
                self.finish()
            except StreamClosedError:
                pass

    async def _write_sse(self, data: dict):
        """Write a server-sent event."""
        try:
            self.write(f"data: {json.dumps(data)}\n\n")
            await self.flush()
        except StreamClosedError:
            # Client disconnected; let outer logic stop cleanly
            raise

    async def _execute_tool_in_kernel(self, kernel, tool_name: str, tool_args: dict, timeout: int = 60) -> dict:
        """Execute a tool in the kernel and return structured result.
        
        Uses timeout protection (from toolslm pattern) to prevent infinite loops.
        """
        code = _build_tool_execution_code(tool_name, tool_args, timeout)
        
        output = []
        
        def output_hook(msg):
            msg_type = msg.get("msg_type", "")
            content = msg.get("content", {})
            if msg_type == "stream" and content.get("name") == "stdout":
                output.append(content.get("text", ""))
            elif msg_type == "execute_result":
                data = content.get("data", {})
                if "text/plain" in data:
                    output.append(data["text/plain"])
        
        import asyncio
        import inspect
        
        try:
            # Get a client from the kernel manager
            client = kernel.client()
            client.start_channels()
            
            async def get_msg_async(timeout=1):
                """Helper to handle both async and sync client APIs."""
                result = client.get_iopub_msg(timeout=timeout)
                if inspect.isawaitable(result):
                    return await result
                return result
            
            try:
                # Execute code and wait for result
                msg_id = client.execute(code, store_history=False, stop_on_error=False)
                
                # Collect output with timeout
                deadline = asyncio.get_event_loop().time() + 60  # 60 second timeout
                
                while True:
                    if asyncio.get_event_loop().time() > deadline:
                        return {"error": "Timeout waiting for kernel response", "status": "error"}
                    
                    try:
                        msg = await get_msg_async(timeout=1)
                    except Exception:
                        continue
                    
                    msg_type = msg.get("msg_type", "")
                    parent_id = msg.get("parent_header", {}).get("msg_id", "")
                    
                    if parent_id != msg_id:
                        continue
                    
                    content = msg.get("content", {})
                    
                    if msg_type == "stream" and content.get("name") == "stdout":
                        output.append(content.get("text", ""))
                    elif msg_type == "execute_result":
                        data = content.get("data", {})
                        if "text/plain" in data:
                            output.append(data["text/plain"])
                    elif msg_type == "error":
                        error_msg = "\n".join(content.get("traceback", ["Unknown error"]))
                        return {"error": error_msg, "status": "error"}
                    elif msg_type in ("execute_reply", "status") and content.get("execution_state") == "idle":
                        # Check if we have output
                        if output:
                            break
                        # Wait a bit more for output
                        try:
                            msg = await get_msg_async(timeout=0.5)
                            if msg.get("parent_header", {}).get("msg_id") == msg_id:
                                if msg.get("msg_type") == "stream":
                                    output.append(msg.get("content", {}).get("text", ""))
                        except Exception:
                            pass
                        break
                
                result_text = "".join(output).strip()
                if result_text:
                    try:
                        return json.loads(result_text)
                    except json.JSONDecodeError:
                        return {"result": {"type": "text", "content": result_text}, "status": "success"}
                else:
                    return {"result": {"type": "text", "content": "No output"}, "status": "success"}
            finally:
                client.stop_channels()
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def _build_system_prompt(self, preceding_code: str, variables: dict, functions: dict, images: list = None, chart_specs: list = None) -> list:
        """Build the system prompt with context as content blocks for caching.
        
        Returns a list of content blocks suitable for Anthropic's system parameter.
        The base instructions are cached (stable across calls), while dynamic
        context (code, variables) is not cached.
        
        Args:
            preceding_code: Code from preceding cells
            variables: Variable info dict
            functions: Function info dict
            images: List of image context dicts with 'data', 'mimeType', 'source', 'cellIndex'
            chart_specs: List of chart spec dicts with 'type', 'spec', 'cellIndex'
        """
        images = images or []
        chart_specs = chart_specs or []
        
        # Base instructions - stable, cacheable (requires ~1024 tokens minimum)
        base_instructions = (
            "You are an AI assistant embedded in a Jupyter notebook. "
            "Help the user with their data science and programming tasks. "
            "When generating code, write Python that can be executed in the notebook. "
            "Be concise and practical. "
            "When you need to perform computations or get data, use the available tools. "
            "Tools return rich results including DataFrames as HTML tables and matplotlib figures as images."
        )
        
        # Add note about images if present
        if images:
            base_instructions += (
                f" You can see {len(images)} image(s) from the notebook - these are outputs from "
                "executed code cells or images attached to markdown cells. Refer to them in your response."
            )
        
        # Add note about chart specs if present
        if chart_specs:
            base_instructions += (
                f" You also have access to {len(chart_specs)} chart specification(s) from the notebook - "
                "these are Vega-Lite (Altair) or Plotly JSON specs that describe visualizations. "
                "Use these specs to understand what the charts show."
            )
        
        blocks = [
            {
                "type": "text",
                "text": base_instructions,
                "cache_control": {"type": "ephemeral"}
            }
        ]
        
        # Dynamic context - not cached since it changes per-cell
        dynamic_parts = []
        
        if preceding_code:
            dynamic_parts.append(f"## Preceding Code Context\n```python\n{preceding_code}\n```")
        
        if variables:
            var_desc = "## Available Variables\n"
            for name, info in variables.items():
                var_desc += f"- `{name}`: {info.get('type', 'unknown')} = {info.get('repr', 'N/A')}\n"
            dynamic_parts.append(var_desc)
        
        if functions:
            func_desc = "## Available Functions (you can call these as tools)\n"
            for name, info in functions.items():
                sig = info.get('signature', '()')
                doc = info.get('docstring', 'No documentation')
                func_desc += f"- `{name}{sig}`: {doc}\n"
            dynamic_parts.append(func_desc)
        
        # Add chart specs as text context (LLMs can understand JSON specs)
        if chart_specs:
            for i, spec in enumerate(chart_specs):
                chart_type = spec.get("type", "unknown")
                cell_idx = spec.get("cellIndex", "?")
                spec_data = spec.get("spec", {})
                
                # Format the spec type nicely
                type_label = "Vega-Lite (Altair)" if chart_type == "vega-lite" else "Plotly"
                
                # Truncate large specs to avoid token overflow
                spec_json = json.dumps(spec_data, indent=2)
                if len(spec_json) > 5000:
                    spec_json = spec_json[:5000] + "\n... (truncated)"
                
                chart_desc = f"## Chart Specification {i+1} ({type_label} from cell {cell_idx})\n```json\n{spec_json}\n```"
                dynamic_parts.append(chart_desc)
        
        if dynamic_parts:
            blocks.append({
                "type": "text", 
                "text": "\n\n".join(dynamic_parts)
            })
        
        # Add images to context (Anthropic format)
        for i, img in enumerate(images):
            source_desc = "cell output" if img.get("source") == "output" else "markdown attachment"
            cell_idx = img.get("cellIndex", "?")
            
            # Add description before image
            blocks.append({
                "type": "text",
                "text": f"## Image {i+1} (from {source_desc} in cell {cell_idx})"
            })
            
            # Add the image
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("mimeType", "image/png"),
                    "data": img.get("data", "")
                }
            })
        
        return blocks

    def _build_tools(self, functions: dict) -> list:
        """Build Anthropic tool definitions from function info."""
        tools = []
        for name, info in functions.items():
            params = info.get('parameters', {})
            # Convert parameters to valid JSON Schema format
            properties = {}
            required = []
            for param_name, param_info in params.items():
                # Convert Python type names to JSON Schema types
                python_type = param_info.get('type', 'string')
                json_type = self._python_type_to_json_schema(python_type)
                properties[param_name] = {
                    "type": json_type,
                    "description": param_info.get('description', param_name)
                }
                # Only add to required if no default value
                if 'default' not in param_info:
                    required.append(param_name)
            
            tool = {
                "name": name,
                "description": info.get('docstring', f"Call the {name} function"),
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
            tools.append(tool)
        return tools
    
    def _python_type_to_json_schema(self, python_type: str) -> str:
        """Convert Python type name to JSON Schema type."""
        type_map = {
            'int': 'integer',
            'float': 'number',
            'str': 'string',
            'bool': 'boolean',
            'list': 'array',
            'dict': 'object',
            'List': 'array',
            'Dict': 'object',
            'None': 'null',
            'NoneType': 'null',
        }
        # Handle generic types like typing.List[int]
        base_type = python_type.split('[')[0]
        return type_map.get(base_type, 'string')


class ToolExecuteHandler(APIHandler):
    """Handler for executing tool calls in the kernel."""

    @authenticated
    async def post(self):
        """Execute a tool call and return the result."""
        data = self.get_json_body() or {}
        if not isinstance(data, dict):
            self.finish(json.dumps({"error": "Invalid JSON body", "status": "error"}))
            return
        tool_name = data.get("name")
        tool_input = data.get("input", {})
        kernel_id = data.get("kernel_id")
        allowed_tools = data.get("allowed_tools")  # Optional list of allowed function names
        
        if not tool_name:
            self.finish(json.dumps({
                "error": "tool name is required",
                "status": "error"
            }))
            return
        
        # Validate tool name format (must be a valid Python identifier)
        if not TOOL_NAME_RE.match(tool_name):
            self.finish(json.dumps({
                "error": f"Invalid tool name: {tool_name}",
                "status": "error"
            }))
            return
        
        if not kernel_id:
            self.finish(json.dumps({
                "error": "kernel_id is required",
                "status": "error"
            }))
            return
        
        # Validate tool name against allowed tools if provided
        if allowed_tools is not None and tool_name not in allowed_tools:
            self.finish(json.dumps({
                "error": f"Tool '{tool_name}' is not in allowed tools",
                "status": "error"
            }))
            return

        try:
            tool_input = _validate_tool_args(tool_input)
        except ValueError as ve:
            self.finish(json.dumps({"error": str(ve), "status": "error"}))
            return
        
        # Get kernel manager from settings
        kernel_manager = self.settings.get("kernel_manager")
        if not kernel_manager:
            self.finish(json.dumps({
                "error": "Kernel manager not available",
                "status": "error"
            }))
            return
        
        try:
            # Get the kernel
            kernel = kernel_manager.get_kernel(kernel_id)
            if not kernel:
                self.finish(json.dumps({
                    "error": f"Kernel {kernel_id} not found",
                    "status": "error"
                }))
                return
            
            timeout = 60  # seconds
            code = _build_tool_execution_code(tool_name, tool_input, timeout)
            
            # Execute code and capture output
            output = []
            
            # Get a client from the kernel manager
            client = kernel.client()
            client.start_channels()
            
            import asyncio
            import inspect
            
            async def get_msg_async(timeout=1):
                """Helper to handle both async and sync client APIs."""
                result = client.get_iopub_msg(timeout=timeout)
                if inspect.isawaitable(result):
                    return await result
                return result
            
            try:
                # Execute code and wait for result
                msg_id = client.execute(code, store_history=False, stop_on_error=False)
                
                # Collect output with timeout
                deadline = asyncio.get_event_loop().time() + 60  # 60 second timeout
                
                while True:
                    if asyncio.get_event_loop().time() > deadline:
                        self.finish(json.dumps({"error": "Timeout", "status": "error"}))
                        return
                    
                    try:
                        msg = await get_msg_async(timeout=1)
                    except Exception:
                        continue
                    
                    msg_type = msg.get("msg_type", "")
                    parent_id = msg.get("parent_header", {}).get("msg_id", "")
                    
                    if parent_id != msg_id:
                        continue
                    
                    content = msg.get("content", {})
                    
                    if msg_type == "stream" and content.get("name") == "stdout":
                        output.append(content.get("text", ""))
                    elif msg_type == "execute_result":
                        data = content.get("data", {})
                        if "text/plain" in data:
                            output.append(data["text/plain"])
                    elif msg_type == "error":
                        error_msg = "\n".join(content.get("traceback", ["Unknown error"]))
                        self.finish(json.dumps({"error": error_msg, "status": "error"}))
                        return
                    elif msg_type in ("execute_reply", "status") and content.get("execution_state") == "idle":
                        if output:
                            break
                        try:
                            msg = await get_msg_async(timeout=0.5)
                            if msg.get("parent_header", {}).get("msg_id") == msg_id:
                                if msg.get("msg_type") == "stream":
                                    output.append(msg.get("content", {}).get("text", ""))
                        except Exception:
                            pass
                        break
                
                # Parse the output
                result_text = "".join(output).strip()
                if result_text:
                    try:
                        result = json.loads(result_text)
                        self.finish(json.dumps(result))
                    except json.JSONDecodeError:
                        self.finish(json.dumps({
                            "result": {"type": "text", "content": result_text},
                            "status": "success"
                        }))
                else:
                    self.finish(json.dumps({
                        "result": {"type": "text", "content": "No output"},
                        "status": "success"
                    }))
            finally:
                client.stop_channels()
                
        except Exception as e:
            self.log.error(f"Error executing tool {tool_name}: {e}")
            self.finish(json.dumps({
                "error": str(e),
                "status": "error"
            }))


class ModelsHandler(APIHandler):
    """Handler for listing available models."""

    @authenticated
    def get(self):
        models = [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
        ]
        self.finish(json.dumps({"models": models}))


def setup_handlers(web_app):
    """Setup API handlers."""
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]
    
    handlers = [
        (url_path_join(base_url, "ai-jup", "prompt"), PromptHandler),
        (url_path_join(base_url, "ai-jup", "tool-execute"), ToolExecuteHandler),
        (url_path_join(base_url, "ai-jup", "models"), ModelsHandler),
    ]
    web_app.add_handlers(host_pattern, handlers)
