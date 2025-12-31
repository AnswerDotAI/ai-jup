/**
 * Signal-based prompt model for streaming AI responses.
 * 
 * Uses Lumino Signals for reactive updates, following jupyter-ai patterns.
 */

import { Signal, ISignal } from '@lumino/signaling';
import { PageConfig } from '@jupyterlab/coreutils';
import type {
  IPromptModel,
  IStreamEvent,
  IPromptContext
} from './tokens';
import { renderToolResult } from './toolResultRenderer';

/**
 * Implementation of IPromptModel with signal-based streaming.
 */
export class PromptModel implements IPromptModel {
  private _state: IPromptModel.ExecutionState = 'idle';
  private _output = '';
  private _abortController: AbortController | null = null;

  private _streamEvent = new Signal<this, IStreamEvent>(this);
  private _outputChanged = new Signal<this, string>(this);
  private _stateChanged = new Signal<this, IPromptModel.ExecutionState>(this);

  /**
   * Signal emitted when streaming events occur.
   */
  get streamEvent(): ISignal<IPromptModel, IStreamEvent> {
    return this._streamEvent;
  }

  /**
   * Signal emitted when the accumulated output changes.
   */
  get outputChanged(): ISignal<IPromptModel, string> {
    return this._outputChanged;
  }

  /**
   * Signal emitted when execution state changes.
   */
  get stateChanged(): ISignal<IPromptModel, IPromptModel.ExecutionState> {
    return this._stateChanged;
  }

  /**
   * Current execution state.
   */
  get state(): IPromptModel.ExecutionState {
    return this._state;
  }

  /**
   * Current accumulated output text.
   */
  get output(): string {
    return this._output;
  }

  /**
   * Execute a prompt and stream the response.
   */
  async executePrompt(
    prompt: string,
    context: IPromptContext,
    options: IPromptModel.IExecuteOptions
  ): Promise<void> {
    this._setState('executing');
    this._output = '';
    this._abortController = new AbortController();

    this._emitEvent({ type: 'start' });

    const baseUrl = PageConfig.getBaseUrl();
    const body = {
      prompt,
      context,
      model: options.model,
      kernel_id: options.kernelId,
      max_steps: options.maxSteps ?? 1
    };

    try {
      const response = await fetch(`${baseUrl}ai-jup/prompt`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body),
        signal: this._abortController.signal
      });

      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const errorBody = await response.json();
          if (errorBody.error) {
            errorMessage = errorBody.error;
          }
        } catch {
          // Response wasn't JSON
        }
        throw new Error(errorMessage);
      }

      this._setState('streaming');
      await this._processStream(response);
      this._setState('idle');
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        this._setState('idle');
        return;
      }
      this._emitEvent({
        type: 'error',
        error: error instanceof Error ? error.message : String(error)
      });
      this._setState('error');
      throw error;
    } finally {
      this._abortController = null;
    }
  }

  /**
   * Process the SSE stream from the server.
   */
  private async _processStream(response: Response): Promise<void> {
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let currentToolCall: { name: string; id: string; input: string } | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const rawLine of lines) {
          const line = rawLine.replace(/\r$/, '');
          if (!line.startsWith('data: ')) continue;

          const data = line.slice(6);
          try {
            const event = JSON.parse(data);
            this._handleServerEvent(event, currentToolCall);

            // Track tool call state
            if (event.tool_call) {
              currentToolCall = {
                name: event.tool_call.name,
                id: event.tool_call.id,
                input: ''
              };
            } else if (event.tool_input && currentToolCall) {
              currentToolCall.input += event.tool_input;
            } else if (event.tool_result) {
              currentToolCall = null;
            }
          } catch {
            // Ignore invalid JSON
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    this._emitEvent({ type: 'done' });
  }

  /**
   * Handle a server-sent event.
   */
  private _handleServerEvent(
    event: Record<string, unknown>,
    currentToolCall: { name: string; id: string; input: string } | null
  ): void {
    if (event.text) {
      const text = event.text as string;
      this._appendOutput(text);
      this._emitEvent({ type: 'text', text });
    } else if (event.error) {
      const error = event.error as string;
      this._appendOutput(`\n\n**Error:** ${error}\n`);
      this._emitEvent({ type: 'error', error });
    } else if (event.tool_call) {
      const toolCall = event.tool_call as { name: string; id: string };
      this._appendOutput(`\n\n🔧 *Calling tool: \`${toolCall.name}\`...*\n`);
      this._emitEvent({
        type: 'tool_call',
        toolCall: { name: toolCall.name, id: toolCall.id }
      });
    } else if (event.tool_input) {
      this._emitEvent({ type: 'tool_input', toolInput: event.tool_input as string });
    } else if (event.tool_result) {
      const tr = event.tool_result as { id: string; name: string; result: unknown };
      const rendered = renderToolResult(tr.result);
      this._appendOutput(rendered);
      this._emitEvent({
        type: 'tool_result',
        toolResult: { id: tr.id, name: tr.name, result: tr.result }
      });
    }
  }

  /**
   * Append text to output and emit change signal.
   */
  private _appendOutput(text: string): void {
    this._output += text;
    this._outputChanged.emit(this._output);
  }

  /**
   * Abort the current execution.
   */
  abort(): void {
    if (this._abortController) {
      this._abortController.abort();
      this._abortController = null;
    }
  }

  /**
   * Reset the model state.
   */
  reset(): void {
    this.abort();
    this._output = '';
    this._setState('idle');
    this._outputChanged.emit(this._output);
  }

  /**
   * Set state and emit signal.
   */
  private _setState(state: IPromptModel.ExecutionState): void {
    if (this._state !== state) {
      this._state = state;
      this._stateChanged.emit(state);
    }
  }

  /**
   * Emit a stream event.
   */
  private _emitEvent(event: IStreamEvent): void {
    this._streamEvent.emit(event);
  }

  /**
   * Dispose of the model.
   */
  dispose(): void {
    this.abort();
    Signal.clearData(this);
  }
}

/**
 * Factory for creating PromptModel instances.
 */
export class PromptModelFactory {
  create(): IPromptModel {
    return new PromptModel();
  }
}
