# ai-jup: AI-Powered Prompt Cells for JupyterLab

A JupyterLab extension that adds AI-powered prompt cells with special syntax for referencing kernel variables and exposing functions as AI-callable tools. Inspired by [fast.ai's Solveit](https://www.fast.ai/posts/2025-11-07-solveit-features.html). This project was a ["vibe-coding" experiment](https://x.com/HamelHusain/status/2006440720001835135?s=20) by Hamel Husain, and only has a small subset of Solveit's features. It's not designed to be a project for long-term development and maintenance. If you do wish to use it, please be sure to follow the GPT v3 license, including releasing all your source code if you modify and use this yourself, including hosting it as an application.

[![CI](https://github.com/hamelsmu/ai-jup/actions/workflows/ci.yml/badge.svg)](https://github.com/hamelsmu/ai-jup/actions/workflows/ci.yml)
![JupyterLab 4.x](https://img.shields.io/badge/JupyterLab-4.x-blue)
![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green)
![License MIT](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **`` $`variable` ``** - Reference kernel variables in prompts (values substituted automatically)
- **`` &`function` ``** - Expose Python functions as AI-callable tools
- **Streaming responses** - Real-time SSE streaming from Anthropic's Claude
- **Full context** - AI sees all preceding code cells and kernel state
- **Tool loop** - AI can call multiple tools in sequence to complete tasks
- **Built-in file tools** - Includes `fastcore.tools` for file exploration and editing

## Quick Start

### 1. Install

```bash
pip install ai_jup
```

Verify the extension is installed:

```bash
jupyter labextension list | grep ai-jup
# Should show: ai-jup v0.1.0 enabled OK
```

### 2. Set your API key

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

To persist across sessions, add to your shell profile:

```bash
# For zsh (macOS default)
echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.zshrc

# For bash
echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.bashrc
```

### 3. Start JupyterLab

```bash
jupyter lab
```

### 4. Try it out

Open [test_syntax.ipynb](test_syntax.ipynb) for a starter notebook demonstrating the `$`variable`` and `&`function`` syntax.

Or create your own:

1. Press `Cmd + Shift + P` (Mac) or `Ctrl + Shift + P` (Windows/Linux) to insert a prompt cell
2. Type: `What is 2 + 2?`
3. Press `Shift + Enter` to execute

You should see the AI respond with streaming text.

### 5. Use variables and functions

```python
# In a code cell, define some data
data = [1, 2, 3, 4, 5]
```

Then in a prompt cell:

```markdown
What is the sum of $`data`?
```

Press `Shift + Enter` to execute.

## Syntax

### `` $`variable` `` - Reference Variables

Use `` $`variable_name` `` to inject the current value of any Python variable into your prompt:

```python
# In a code cell
sales_data = [
    {'product': 'Widget A', 'units': 150, 'price': 25.99},
    {'product': 'Widget B', 'units': 89, 'price': 45.50},
]
```

```markdown
Given $`sales_data`, which product has the highest revenue?
```

The AI sees the actual data and can provide specific analysis.

### `` &`function` `` - Expose Functions as Tools

Use `` &`function_name` `` to let the AI call Python functions during its response:

```python
# In a code cell
def calculate_revenue(data: list) -> float:
    """Calculate total revenue from sales data."""
    return sum(item['units'] * item['price'] for item in data)

def top_seller(data: list) -> dict:
    """Find the product with the most units sold."""
    return max(data, key=lambda x: x['units'])
```

```markdown
Use &`calculate_revenue` and &`top_seller` to analyze $`sales_data`.
```

The AI can call these functions, see the results, and incorporate them into its response.

## Built-in File Tools

ai-jup includes [fastcore.tools](https://github.com/AnswerDotAI/fastcore) for file exploration and editing:

```python
from fastcore.tools import view, rg, sed, create, str_replace, insert
```

| Tool | Description |
|------|-------------|
| `view(path, view_range?, nums?)` | View directory or file contents with optional line range |
| `rg(argstr)` | Run ripgrep to search for patterns |
| `sed(argstr)` | Run sed for reading sections of files |
| `create(path, file_text, overwrite?)` | Create a new file with given content |
| `str_replace(path, old_str, new_str)` | Replace first occurrence in file |
| `insert(path, insert_line, new_str)` | Insert text at specified line number |

### Example: Exploring a Codebase

```python
# Clone a repo to explore
!git clone https://github.com/AnswerDotAI/fastcore --depth 1 -q
repo_path = 'fastcore'

from fastcore.tools import view, rg
```

```markdown
Use &`view` to explore $`repo_path` and tell me what this library does.
Then use &`rg` to find all decorator definitions.
```

The AI will:
1. Call `view('fastcore')` to see the directory structure
2. Call `view('fastcore/fastcore/basics.py')` to read key files
3. Call `rg('"def.*decorator" fastcore/')` to search for patterns
4. Synthesize findings into a coherent explanation

## How It Works

### Prompt Cells

Prompt cells are markdown cells with special metadata (`ai_jup.isPromptCell: true`). They're visually distinguished with a colored border and "AI Prompt" prefix.

### Context Gathering

When you execute a prompt cell, ai-jup:

1. **Collects preceding code** - All code cells above the prompt are gathered
2. **Resolves `` $`variables` ``** - Queries the kernel for each variable's type and repr
3. **Gathers `` &`function` `` metadata** - Gets signatures, docstrings, and parameter info
4. **Builds tool definitions** - Converts functions to Anthropic tool format

### Tool Execution Loop

When the AI calls a tool:

1. The tool call is sent to the Jupyter kernel
2. The function executes with the provided arguments
3. Results are returned to the AI (supports text, HTML, and images)
4. The AI can make additional tool calls or finish its response

The loop continues for up to 5 iterations (configurable via `max_steps`).

### Rich Output Handling

Tool results are automatically formatted:

- **DataFrames** → Rendered as HTML tables
- **Matplotlib figures** → Converted to inline PNG images
- **Text** → Displayed in code blocks
- **Errors** → Shown with clear error messages

## Keyboard Shortcuts

JupyterLab has two modes:
- **Command mode** (blue cell border): Press `Esc` to enter. Navigate and manage cells.
- **Edit mode** (green cell border): Press `Enter` to enter. Edit cell contents.

### Command Mode Shortcuts

Just like `M` converts a cell to Markdown and `Y` converts to code, you can use:

| Shortcut | Action |
|----------|--------|
| `P` | Convert current cell to AI prompt cell |
| `Cmd + Shift + P` (Mac) / `Ctrl + Shift + P` (Windows/Linux) | Insert new prompt cell below |

### Edit Mode Shortcuts

| Shortcut | Action |
|----------|--------|
| `Shift + Enter` | Execute prompt cell (streams AI response) |

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |

### Supported Models

- **Claude Sonnet 4** (default) - `claude-sonnet-4-20250514`
- **Claude 3.5 Sonnet** - `claude-3-5-sonnet-20241022`
- **Claude 3 Haiku** - `claude-3-haiku-20240307`

To change the model, edit the cell metadata:

```json
{
  "ai_jup": {
    "isPromptCell": true,
    "model": "claude-3-haiku-20240307"
  }
}
```

## Development

```bash
git clone https://github.com/hamelsmu/ai-jup.git
cd ai-jup
just install   # Install in dev mode with live reload
just test      # Run all tests
just lab       # Start JupyterLab
just --list    # See all commands
```

Requires [just](https://github.com/casey/just) (`brew install just` on macOS).

## Architecture

```
ai-jup/
├── src/                        # TypeScript frontend
│   ├── index.ts                # Extension entry point
│   ├── promptCell.ts           # Prompt cell management
│   ├── kernelConnector.ts      # Kernel introspection
│   ├── promptParser.ts         # $`variable` and &`function` parsing
│   ├── toolResultRenderer.ts   # Tool result formatting
│   └── *.test.ts               # Jest tests
├── ai_jup/                     # Python backend
│   ├── handlers.py             # API endpoints
│   └── __init__.py             # Server extension setup
├── tests/                      # Python test suite
├── style/                      # CSS styles
└── justfile                    # Development commands
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ai-jup/prompt` | POST | Stream AI response with tool loop |
| `/ai-jup/tool-execute` | POST | Execute a single tool call |
| `/ai-jup/models` | GET | List available models |

## Troubleshooting

### Extension not loading after install

If you installed ai-jup but it's not working:

```bash
# Verify extension is installed
jupyter labextension list | grep ai-jup

# Restart JupyterLab (required after first install)
# Close JupyterLab and run:
jupyter lab
```

### "ANTHROPIC_API_KEY not set"

The API key must be set in the environment *before* starting JupyterLab:

```bash
export ANTHROPIC_API_KEY="your-key-here"
jupyter lab
```

If you set the key after JupyterLab started, you need to restart it.

### "anthropic package not installed"

```bash
pip install anthropic
```

### Keyboard shortcuts not working

Make sure you're in command mode (press `Esc` first), then try the shortcut. If shortcuts still don't work, check for conflicts in Settings → Advanced Settings → Keyboard Shortcuts.

### Tool execution fails

Ensure the function is defined in the kernel before referencing it with `` &`functionname` ``. Run the code cell that defines the function first, then execute the prompt cell.

## Requirements

- Python ≥ 3.8
- JupyterLab ≥ 4.0
- anthropic ≥ 0.50.0
- fastcore ≥ 1.7.0

## License

GPT v3 license - see [LICENSE](LICENSE) for details.

## Credits

- Inspired by [fast.ai's Solveit](https://www.fast.ai/posts/2025-11-07-solveit-features.html)
- Uses [fastcore.tools](https://github.com/AnswerDotAI/fastcore) for file operations
- Powered by [Anthropic Claude](https://www.anthropic.com/)
