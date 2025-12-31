/**
 * Prompt cell management and execution.
 */

import { NotebookPanel, NotebookActions } from '@jupyterlab/notebook';
import { Cell, ICellModel, MarkdownCell } from '@jupyterlab/cells';
import { KernelConnector, VariableInfo, FunctionInfo } from './kernelConnector';
import { parsePrompt, processPrompt } from './promptParser';
import { renderToolResult } from './toolResultRenderer';

const PROMPT_CELL_CLASS = 'ai-jup-prompt-cell';
const PROMPT_OUTPUT_CLASS = 'ai-jup-prompt-output';
const PROMPT_METADATA_KEY = 'ai_jup';
const ACTIVE_REQUEST_KEY = 'ai_jup_active_request';

interface PromptMetadata {
  isPromptCell: boolean;
  model?: string;
}

/**
 * Manages prompt cells within notebooks.
 */
export class PromptCellManager {
  private _connectors: Map<string, KernelConnector> = new Map();

  /**
   * Set up a notebook for prompt cell handling.
   */
  setupNotebook(panel: NotebookPanel, connector: KernelConnector): void {
    const notebookId = panel.id;
    this._connectors.set(notebookId, connector);

    // Style existing prompt cells
    const notebook = panel.content;
    for (let i = 0; i < notebook.widgets.length; i++) {
      const cell = notebook.widgets[i];
      if (this._isPromptCell(cell.model)) {
        cell.addClass(PROMPT_CELL_CLASS);
      }
    }

    // Listen for cell changes to style new prompt cells
    const cells = notebook.model?.cells;
    const onCellsChanged = (_: unknown, args: { type: string; newValues: ICellModel[] }) => {
      if (args.type === 'add') {
        for (const cellModel of args.newValues) {
          if (this._isPromptCell(cellModel)) {
            // Find the index by iterating through cells
            let idx = -1;
            for (let i = 0; i < notebook.model!.cells.length; i++) {
              if (notebook.model!.cells.get(i) === cellModel) {
                idx = i;
                break;
              }
            }
            if (idx >= 0 && idx < notebook.widgets.length) {
              notebook.widgets[idx].addClass(PROMPT_CELL_CLASS);
            }
          }
        }
      }
    };

    if (cells) {
      cells.changed.connect(onCellsChanged);
    }

    // Clean up when notebook is closed
    panel.disposed.connect(() => {
      this._connectors.delete(notebookId);
      if (cells) {
        cells.changed.disconnect(onCellsChanged);
      }
    });
  }

  /**
   * Insert a new prompt cell below the active cell.
   */
  insertPromptCell(panel: NotebookPanel): void {
    const notebook = panel.content;

    // Insert a markdown cell below
    NotebookActions.insertBelow(notebook);

    const activeIndex = notebook.activeCellIndex;
    const cell = notebook.widgets[activeIndex];
    const model = cell.model;

    // Mark as prompt cell
    model.setMetadata(PROMPT_METADATA_KEY, {
      isPromptCell: true,
      model: 'claude-sonnet-4-20250514'
    } as PromptMetadata);

    // Change to markdown type for the prompt
    if (notebook.model) {
      const cellData = model.toJSON();
      cellData.cell_type = 'markdown';
      cellData.source = '**AI Prompt:** ';
      notebook.model.sharedModel.deleteCell(activeIndex);
      notebook.model.sharedModel.insertCell(activeIndex, cellData);
    }

    // Add styling class
    const newCell = notebook.widgets[activeIndex];
    newCell.addClass(PROMPT_CELL_CLASS);

    // Focus the cell for editing
    notebook.activeCellIndex = activeIndex;
    notebook.mode = 'edit';
  }

  /**
   * Execute the current prompt cell.
   */
  async executePromptCell(panel: NotebookPanel): Promise<void> {
    const notebook = panel.content;
    const activeCell = notebook.activeCell;

    if (!activeCell || !this._isPromptCell(activeCell.model)) {
      console.log('Not a prompt cell');
      return;
    }

    const connector = this._connectors.get(panel.id);
    if (!connector) {
      console.error('No kernel connector found');
      return;
    }

    // Get model from cell metadata
    const metadata = activeCell.model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
    const model = metadata?.model || 'claude-sonnet-4-20250514';

    // Get kernel ID for tool execution
    const kernelId = panel.sessionContext.session?.kernel?.id;

    // Get the prompt text
    const promptText = activeCell.model.sharedModel.getSource();

    // Remove the "**AI Prompt:** " prefix if present
    const cleanPrompt = promptText.replace(/^\*\*AI Prompt:\*\*\s*/i, '');

    // Parse for variable and function references
    const parsed = parsePrompt(cleanPrompt);

    // Gather context
    const context = await this._gatherContext(panel, connector, parsed);

    // Process the prompt (substitute variables)
    const variableValues: Record<string, string> = {};
    for (const [name, info] of Object.entries(context.variables)) {
      variableValues[name] = (info as VariableInfo).repr;
    }
    const processedPrompt = processPrompt(cleanPrompt, variableValues);

    // Insert output cell
    const outputCell = this._insertOutputCell(panel, activeCell);

    // Call the AI backend
    await this._callAI(processedPrompt, context, outputCell, model, kernelId, connector);
  }

  /**
   * Gather context for the prompt including preceding code and referenced items.
   */
  private async _gatherContext(
    panel: NotebookPanel,
    connector: KernelConnector,
    parsed: ReturnType<typeof parsePrompt>
  ): Promise<{
    preceding_code: string;
    variables: Record<string, VariableInfo>;
    functions: Record<string, FunctionInfo>;
  }> {
    const notebook = panel.content;
    const activeIndex = notebook.activeCellIndex;

    // Get preceding code cells
    const precedingCode: string[] = [];
    for (let i = 0; i < activeIndex; i++) {
      const cell = notebook.widgets[i];
      if (cell.model.type === 'code') {
        precedingCode.push(cell.model.sharedModel.getSource());
      }
    }

    // Get referenced variables
    const variables: Record<string, VariableInfo> = {};
    for (const varName of parsed.variables) {
      const info = await connector.getVariable(varName);
      if (info) {
        variables[varName] = info;
      }
    }

    // Get referenced functions
    const functions: Record<string, FunctionInfo> = {};
    for (const funcName of parsed.functions) {
      const info = await connector.getFunction(funcName);
      if (info) {
        functions[funcName] = info;
      }
    }

    return {
      preceding_code: precedingCode.join('\n\n'),
      variables,
      functions
    };
  }

  /**
   * Insert a markdown cell for the AI output.
   */
  private _insertOutputCell(panel: NotebookPanel, promptCell: Cell): Cell {
    const notebook = panel.content;
    const promptIndex = notebook.widgets.indexOf(promptCell);

    // Check if next cell is already an output cell
    if (promptIndex + 1 < notebook.widgets.length) {
      const nextCell = notebook.widgets[promptIndex + 1];
      if (nextCell.hasClass(PROMPT_OUTPUT_CLASS)) {
        // Reuse existing output cell
        nextCell.model.sharedModel.setSource('<div class="ai-jup-loading">Generating response...</div>');
        return nextCell;
      }
    }

    // Insert new markdown cell
    notebook.activeCellIndex = promptIndex;
    NotebookActions.insertBelow(notebook);

    const outputIndex = promptIndex + 1;
    const outputCell = notebook.widgets[outputIndex];

    // Set up as output cell
    if (notebook.model) {
      const cellData = outputCell.model.toJSON();
      cellData.cell_type = 'markdown';
      cellData.source = '<div class="ai-jup-loading">Generating response...</div>';
      notebook.model.sharedModel.deleteCell(outputIndex);
      notebook.model.sharedModel.insertCell(outputIndex, cellData);
    }

    const newOutputCell = notebook.widgets[outputIndex];
    newOutputCell.addClass(PROMPT_OUTPUT_CLASS);

    return newOutputCell;
  }

  /**
   * Call the AI backend and stream the response.
   * Now supports server-side tool loop with max_steps.
   */
  private async _callAI(
    prompt: string,
    context: {
      preceding_code: string;
      variables: Record<string, VariableInfo>;
      functions: Record<string, FunctionInfo>;
    },
    outputCell: Cell,
    model: string,
    kernelId: string | undefined,
    connector: KernelConnector
  ): Promise<void> {
    // Prevent concurrent requests on the same output cell
    const existingRequest = outputCell.model.getMetadata(ACTIVE_REQUEST_KEY);
    if (existingRequest) {
      console.log('Request already in progress for this cell');
      return;
    }
    outputCell.model.setMetadata(ACTIVE_REQUEST_KEY, true);

    const baseUrl = (window as unknown as { jupyterBaseUrl?: string }).jupyterBaseUrl || '';
    const url = `${baseUrl}/ai-jup/prompt`;

    // Set up abort controller to cancel request if cell is disposed
    const controller = new AbortController();
    const abortOnDispose = () => controller.abort();
    outputCell.disposed.connect(abortOnDispose);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          prompt,
          model,
          kernel_id: kernelId,
          max_steps: 5, // Enable server-side tool loop
          context: {
            preceding_code: context.preceding_code,
            variables: context.variables,
            functions: context.functions
          }
        }),
        credentials: 'include',
        signal: controller.signal
      });

      if (!response.ok) {
        // Try to extract error message from JSON response body
        let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const errorBody = await response.json();
          if (errorBody.error) {
            errorMessage = errorBody.error;
          }
        } catch {
          // Response wasn't JSON, use default message
        }
        throw new Error(errorMessage);
      }

      // Handle SSE stream
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let outputText = '';
      let buffer = '';
      let currentToolCall: { name: string; id: string; input: string } | null = null;

      while (true) {
        let readResult: ReadableStreamReadResult<Uint8Array>;
        try {
          readResult = await reader.read();
        } catch (e) {
          // Network interruption mid-stream
          if (outputCell.isDisposed) break;
          throw e;
        }
        const { done, value } = readResult;
        if (done || outputCell.isDisposed) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE events
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const rawLine of lines) {
          // Trim CRLF for proxy compatibility
          const line = rawLine.replace(/\r$/, '');
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const event = JSON.parse(data);
              if (event.text) {
                outputText += event.text;
                outputCell.model.sharedModel.setSource(outputText);
              } else if (event.error) {
                outputText += `\n\n**Error:** ${event.error}\n`;
                outputCell.model.sharedModel.setSource(outputText);
              } else if (event.done) {
                // Server-side tool loop handles execution
                // If tools were requested but no kernel available, show error
                if (currentToolCall && !kernelId) {
                  outputText += '\n**Tool Error:** Tools require an active kernel.\n';
                  outputCell.model.sharedModel.setSource(outputText);
                }
              } else if (event.tool_call) {
                currentToolCall = {
                  name: event.tool_call.name,
                  id: event.tool_call.id,
                  input: ''
                };
                outputText += `\n\n🔧 *Calling tool: \`${event.tool_call.name}\`...*\n`;
                outputCell.model.sharedModel.setSource(outputText);
              } else if (event.tool_input && currentToolCall) {
                currentToolCall.input += event.tool_input;
              } else if (event.tool_result) {
                // Handle server-side tool execution result
                const tr = event.tool_result;
                const rendered = renderToolResult(tr.result);
                outputText += rendered;
                outputCell.model.sharedModel.setSource(outputText);
                // Reset for potential next tool call
                currentToolCall = null;
              }
            } catch {
              // Ignore invalid JSON
            }
          }
        }
      }

      // Render markdown
      if (!outputCell.isDisposed && outputCell instanceof MarkdownCell) {
        outputCell.rendered = true;
      }
    } catch (error: unknown) {
      // Don't show error if request was aborted (cell/notebook closed)
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }
      if (!outputCell.isDisposed) {
        outputCell.model.sharedModel.setSource(
          `**Error:** Failed to connect to AI backend.\n\n${String(error)}`
        );
        if (outputCell instanceof MarkdownCell) {
          outputCell.rendered = true;
        }
      }
    } finally {
      outputCell.disposed.disconnect(abortOnDispose);
      // Clear the active request flag
      if (!outputCell.isDisposed) {
        outputCell.model.deleteMetadata(ACTIVE_REQUEST_KEY);
      }
    }
  }

  /**
   * Check if a cell model is a prompt cell.
   */
  private _isPromptCell(model: ICellModel): boolean {
    const metadata = model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
    return metadata?.isPromptCell === true;
  }
}
