/**
 * Dependency injection tokens for ai-jup extension.
 * 
 * Following JupyterLab's plugin architecture pattern, these tokens
 * allow loose coupling between components and enable testing/mocking.
 */

import { Token } from '@lumino/coreutils';
import { ISignal } from '@lumino/signaling';
import { NotebookPanel } from '@jupyterlab/notebook';
import { Cell } from '@jupyterlab/cells';
import { KernelMessage } from '@jupyterlab/services';

/**
 * Variable information from kernel introspection.
 */
export interface IVariableInfo {
  name: string;
  type: string;
  repr: string;
  value?: unknown;
}

/**
 * Parameter information for function introspection.
 */
export interface IParameterInfo {
  type: string;
  description: string;
  default?: string;
}

/**
 * Function information from kernel introspection.
 */
export interface IFunctionInfo {
  name: string;
  signature: string;
  docstring: string;
  parameters: Record<string, IParameterInfo>;
  return_type?: string;
}

/**
 * Interface for kernel connector.
 * Provides kernel introspection and code execution capabilities.
 */
export interface IKernelConnector {
  /**
   * Whether the kernel is currently available.
   */
  readonly kernelAvailable: boolean;

  /**
   * Execute code silently and capture output.
   */
  execute(
    code: string,
    onOutput?: (msg: KernelMessage.IIOPubMessage) => void
  ): Promise<KernelMessage.IExecuteReplyMsg | null>;

  /**
   * Execute code and return stdout output as string.
   */
  executeAndCapture(code: string): Promise<string>;

  /**
   * Get information about a variable in the kernel.
   */
  getVariable(name: string): Promise<IVariableInfo | null>;

  /**
   * Get information about a function in the kernel.
   */
  getFunction(name: string): Promise<IFunctionInfo | null>;
}

/**
 * Stream event types for prompt execution.
 */
export type StreamEventType =
  | 'start'
  | 'text'
  | 'tool_call'
  | 'tool_input'
  | 'tool_result'
  | 'error'
  | 'done';

/**
 * Stream event emitted during prompt execution.
 */
export interface IStreamEvent {
  type: StreamEventType;
  /** Text content for 'text' events */
  text?: string;
  /** Tool call info for 'tool_call' events */
  toolCall?: {
    name: string;
    id: string;
  };
  /** Tool input JSON for 'tool_input' events */
  toolInput?: string;
  /** Tool result for 'tool_result' events */
  toolResult?: {
    id: string;
    name: string;
    result: unknown;
  };
  /** Error message for 'error' events */
  error?: string;
}

/**
 * Image extracted from notebook cells for multimodal context.
 */
export interface IImageContext {
  /** Base64 encoded image data */
  data: string;
  /** MIME type (image/png, image/jpeg, image/gif) */
  mimeType: 'image/png' | 'image/jpeg' | 'image/gif';
  /** Source of the image */
  source: 'output' | 'attachment';
  /** Cell index where the image was found */
  cellIndex: number;
}

/**
 * Chart specification extracted from notebook cells for declarative viz context.
 * Supports Vega-Lite (Altair) and Plotly JSON specs.
 */
export interface IChartSpec {
  /** Chart library type */
  type: 'vega-lite' | 'plotly';
  /** The JSON specification */
  spec: Record<string, unknown>;
  /** Cell index where the chart was found */
  cellIndex: number;
}

/**
 * Prompt execution context containing gathered information.
 */
export interface IPromptContext {
  preceding_code: string;
  variables: Record<string, IVariableInfo>;
  functions: Record<string, IFunctionInfo>;
  /** Images from preceding cells (outputs and markdown attachments) */
  images?: IImageContext[];
  /** Chart specs from preceding cells (Vega-Lite, Plotly) */
  chartSpecs?: IChartSpec[];
}

/**
 * Interface for the prompt model.
 * Manages prompt state and emits streaming events.
 */
export interface IPromptModel {
  /**
   * Signal emitted when streaming events occur.
   */
  readonly streamEvent: ISignal<IPromptModel, IStreamEvent>;

  /**
   * Signal emitted when the accumulated output changes.
   */
  readonly outputChanged: ISignal<IPromptModel, string>;

  /**
   * Signal emitted when execution state changes.
   */
  readonly stateChanged: ISignal<IPromptModel, IPromptModel.ExecutionState>;

  /**
   * Current execution state.
   */
  readonly state: IPromptModel.ExecutionState;

  /**
   * Current accumulated output text.
   */
  readonly output: string;

  /**
   * Execute a prompt and stream the response.
   */
  executePrompt(
    prompt: string,
    context: IPromptContext,
    options: IPromptModel.IExecuteOptions
  ): Promise<void>;

  /**
   * Abort the current execution.
   */
  abort(): void;

  /**
   * Reset the model state.
   */
  reset(): void;
}

export namespace IPromptModel {
  export type ExecutionState = 'idle' | 'executing' | 'streaming' | 'error';

  export interface IExecuteOptions {
    model: string;
    kernelId?: string;
    maxSteps?: number;
  }
}

/**
 * Interface for prompt cell manager.
 * Manages prompt cells within notebooks.
 */
export interface IPromptCellManager {
  /**
   * Set up a notebook for prompt cell handling.
   */
  setupNotebook(panel: NotebookPanel, connector: IKernelConnector): void;

  /**
   * Insert a new prompt cell below the current cell.
   */
  insertPromptCell(panel: NotebookPanel): void;

  /**
   * Execute the current prompt cell.
   */
  executePromptCell(panel: NotebookPanel): Promise<void>;

  /**
   * Check if a cell is a prompt cell.
   */
  isPromptCell(cell: Cell): boolean;
}

/**
 * Extension settings interface.
 */
export interface IExtensionSettings {
  /**
   * Default model to use for prompts.
   */
  defaultModel: string;

  /**
   * Maximum tool execution steps.
   */
  maxToolSteps: number;

  /**
   * Whether to show the convert to cells button.
   */
  showConvertButton: boolean;
}

/**
 * Token for the kernel connector factory.
 */
export const IKernelConnectorFactory = new Token<IKernelConnectorFactory>(
  'ai-jup:IKernelConnectorFactory',
  'Factory for creating kernel connectors'
);

export interface IKernelConnectorFactory {
  /**
   * Create a kernel connector for a session context.
   */
  create(sessionContext: unknown): IKernelConnector;
}

/**
 * Token for the prompt cell manager.
 */
export const IPromptCellManager = new Token<IPromptCellManager>(
  'ai-jup:IPromptCellManager',
  'Manages prompt cells within notebooks'
);

/**
 * Token for the prompt model factory.
 */
export const IPromptModelFactory = new Token<IPromptModelFactory>(
  'ai-jup:IPromptModelFactory',
  'Factory for creating prompt models'
);

export interface IPromptModelFactory {
  /**
   * Create a new prompt model instance.
   */
  create(): IPromptModel;
}

/**
 * Token for extension settings.
 */
export const IExtensionSettings = new Token<IExtensionSettings>(
  'ai-jup:IExtensionSettings',
  'Extension configuration settings'
);
