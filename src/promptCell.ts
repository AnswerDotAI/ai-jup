/**
 * Prompt cell management and execution.
 */

import { NotebookPanel, NotebookActions } from '@jupyterlab/notebook';
import { Cell, ICellModel, MarkdownCell } from '@jupyterlab/cells';
import { ICodeCellModel, isCodeCellModel } from '@jupyterlab/cells';
import type {
  IPromptCellManager,
  IKernelConnector,
  IPromptModel,
  IPromptContext,
  IVariableInfo,
  IFunctionInfo,
  IExtensionSettings,
  IImageContext,
  IChartSpec
} from './tokens';
import { parsePrompt, processPrompt } from './promptParser';
import { PromptModel } from './promptModel';

/** Supported image MIME types for multimodal context */
const IMAGE_MIME_TYPES = ['image/png', 'image/jpeg', 'image/gif'] as const;
type ImageMimeType = (typeof IMAGE_MIME_TYPES)[number];

/** MIME type patterns for declarative chart specs */
const VEGALITE_MIME_PATTERN = /^application\/vnd\.vegalite\.v\d+\+json$/;
const PLOTLY_MIME = 'application/vnd.plotly.v1+json';

const PROMPT_CELL_CLASS = 'ai-jup-prompt-cell';
const PROMPT_OUTPUT_CLASS = 'ai-jup-prompt-output';
const PROMPT_METADATA_KEY = 'ai_jup';

interface PromptMetadata {
  isPromptCell: boolean;
  model?: string;
}

/**
 * Manages prompt cells within notebooks.
 * Implements IPromptCellManager for dependency injection.
 */
export class PromptCellManager implements IPromptCellManager {
  private _connectors: Map<string, IKernelConnector> = new Map();
  private _settings: IExtensionSettings | null = null;

  /**
   * Set the settings instance.
   */
  setSettings(settings: IExtensionSettings): void {
    this._settings = settings;
  }

  /**
   * Set up a notebook for prompt cell handling.
   */
  setupNotebook(panel: NotebookPanel, connector: IKernelConnector): void {
    const notebookId = panel.id;
    this._connectors.set(notebookId, connector);

    const notebook = panel.content;
    
    // Style all prompt cells - works with JupyterLab 4 windowing
    const stylePromptCells = () => {
      if (panel.isDisposed || !notebook.model) {
        return;
      }
      const cellCount = notebook.model.cells.length;
      console.log(`[ai-jup] Styling prompt cells, ${cellCount} cells in model, ${notebook.widgets.length} widgets`);
      
      for (let i = 0; i < cellCount; i++) {
        const cellModel = notebook.model.cells.get(i);
        if (this._isPromptCellModel(cellModel)) {
          console.log(`[ai-jup] Found prompt cell at index ${i}`);
          // Widget may not exist yet due to windowing, check bounds
          if (i < notebook.widgets.length) {
            const cell = notebook.widgets[i];
            if (cell && !cell.hasClass(PROMPT_CELL_CLASS)) {
              cell.addClass(PROMPT_CELL_CLASS);
              console.log(`[ai-jup] Added class to cell ${i}`);
            }
          }
        }
      }
    };

    // Initial styling
    stylePromptCells();

    // Re-style when cells scroll into view (for windowing mode)
    const onActiveCellChanged = () => {
      stylePromptCells();
    };
    notebook.activeCellChanged.connect(onActiveCellChanged);

    // Listen for cell changes to style new prompt cells
    const cells = notebook.model?.cells;
    const onCellsChanged = () => {
      // Defer to allow widgets to be created
      requestAnimationFrame(() => stylePromptCells());
    };

    if (cells) {
      cells.changed.connect(onCellsChanged);
    }

    // Clean up when notebook is closed
    panel.disposed.connect(() => {
      this._connectors.delete(notebookId);
      notebook.activeCellChanged.disconnect(onActiveCellChanged);
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

    if (!activeCell || !this._isPromptCellModel(activeCell.model)) {
      console.log('Not a prompt cell');
      return;
    }

    const connector = this._connectors.get(panel.id);
    if (!connector) {
      console.error('No kernel connector found');
      return;
    }

    // Get model from cell metadata or settings
    const metadata = activeCell.model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
    const defaultModel = this._settings?.defaultModel ?? 'claude-sonnet-4-20250514';
    const model = metadata?.model || defaultModel;

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
      variableValues[name] = (info as IVariableInfo).repr;
    }
    const processedPrompt = processPrompt(cleanPrompt, variableValues);

    // Insert output cell
    const outputCell = this._insertOutputCell(panel, activeCell);

    // Call the AI backend
    await this._callAI(panel, processedPrompt, context, outputCell, model, kernelId);
  }

  /**
   * Gather context for the prompt including preceding code and referenced items.
   */
  private async _gatherContext(
    panel: NotebookPanel,
    connector: IKernelConnector,
    parsed: ReturnType<typeof parsePrompt>
  ): Promise<IPromptContext> {
    const notebook = panel.content;
    const activeIndex = notebook.activeCellIndex;

    // Get preceding code cells and extract images/chart specs from outputs
    const precedingCode: string[] = [];
    const images: IImageContext[] = [];
    const chartSpecs: IChartSpec[] = [];

    for (let i = 0; i < activeIndex; i++) {
      const cell = notebook.widgets[i];
      const cellModel = cell.model;

      if (cellModel.type === 'code') {
        precedingCode.push(cellModel.sharedModel.getSource());
        // Extract images and chart specs from code cell outputs
        if (isCodeCellModel(cellModel)) {
          this._extractImagesFromCodeCell(cellModel, i, images);
          this._extractChartSpecsFromCodeCell(cellModel, i, chartSpecs);
        }
      } else if (cellModel.type === 'markdown') {
        // Extract images from markdown cell attachments
        this._extractImagesFromMarkdownCell(cellModel, i, images);
      }
    }

    // Get referenced variables
    const variables: Record<string, IVariableInfo> = {};
    for (const varName of parsed.variables) {
      const info = await connector.getVariable(varName);
      if (info) {
        variables[varName] = info;
      }
    }

    // Get referenced functions
    const functions: Record<string, IFunctionInfo> = {};
    for (const funcName of parsed.functions) {
      const info = await connector.getFunction(funcName);
      if (info) {
        functions[funcName] = info;
      }
    }

    return {
      preceding_code: precedingCode.join('\n\n'),
      variables,
      functions,
      images: images.length > 0 ? images : undefined,
      chartSpecs: chartSpecs.length > 0 ? chartSpecs : undefined
    };
  }

  /**
   * Extract images from code cell outputs.
   */
  private _extractImagesFromCodeCell(
    cellModel: ICodeCellModel,
    cellIndex: number,
    images: IImageContext[]
  ): void {
    const outputs = cellModel.outputs;
    if (!outputs) {
      return;
    }

    for (let j = 0; j < outputs.length; j++) {
      const outputModel = outputs.get(j);
      const data = outputModel.data;

      // Check each supported image MIME type
      for (const mimeType of IMAGE_MIME_TYPES) {
        const imageData = data[mimeType];
        if (imageData && typeof imageData === 'string') {
          images.push({
            data: imageData,
            mimeType: mimeType as ImageMimeType,
            source: 'output',
            cellIndex
          });
          break; // Only take the first matching image type per output
        }
      }
    }
  }

  /**
   * Extract images from markdown cell attachments.
   */
  private _extractImagesFromMarkdownCell(
    cellModel: ICellModel,
    cellIndex: number,
    images: IImageContext[]
  ): void {
    // Attachments are stored in cell metadata under 'attachments'
    const attachments = cellModel.getMetadata('attachments') as
      | Record<string, Record<string, string>>
      | undefined;

    if (!attachments) {
      return;
    }

    // Iterate through each attachment
    for (const [_filename, mimeData] of Object.entries(attachments)) {
      if (!mimeData || typeof mimeData !== 'object') {
        continue;
      }

      // Check each supported image MIME type
      for (const mimeType of IMAGE_MIME_TYPES) {
        const imageData = mimeData[mimeType];
        if (imageData && typeof imageData === 'string') {
          images.push({
            data: imageData,
            mimeType: mimeType as ImageMimeType,
            source: 'attachment',
            cellIndex
          });
          break; // Only take the first matching image type per attachment
        }
      }
    }
  }

  /**
   * Extract chart specs (Vega-Lite, Plotly) from code cell outputs.
   */
  private _extractChartSpecsFromCodeCell(
    cellModel: ICodeCellModel,
    cellIndex: number,
    chartSpecs: IChartSpec[]
  ): void {
    const outputs = cellModel.outputs;
    if (!outputs) {
      return;
    }

    for (let j = 0; j < outputs.length; j++) {
      const outputModel = outputs.get(j);
      const data = outputModel.data;

      // Check for Vega-Lite specs (Altair outputs)
      for (const mimeType of Object.keys(data)) {
        if (VEGALITE_MIME_PATTERN.test(mimeType)) {
          const specData = data[mimeType];
          if (specData && typeof specData === 'object') {
            chartSpecs.push({
              type: 'vega-lite',
              spec: specData as Record<string, unknown>,
              cellIndex
            });
          }
          break;
        }
      }

      // Check for Plotly specs
      const plotlyData = data[PLOTLY_MIME];
      if (plotlyData && typeof plotlyData === 'object') {
        chartSpecs.push({
          type: 'plotly',
          spec: plotlyData as Record<string, unknown>,
          cellIndex
        });
      }
    }
  }

  /**
   * Insert a markdown cell for the AI output.
   * Always creates a new cell for each execution.
   */
  private _insertOutputCell(panel: NotebookPanel, promptCell: Cell): Cell {
    const notebook = panel.content;
    const promptIndex = notebook.widgets.indexOf(promptCell);

    // Find where to insert - after the prompt cell and any existing output cells
    let insertAfterIndex = promptIndex;
    for (let i = promptIndex + 1; i < notebook.widgets.length; i++) {
      if (notebook.widgets[i].hasClass(PROMPT_OUTPUT_CLASS)) {
        insertAfterIndex = i;
      } else {
        break;
      }
    }

    // Insert new markdown cell after the last output (or after prompt if none)
    notebook.activeCellIndex = insertAfterIndex;
    NotebookActions.insertBelow(notebook);

    const outputIndex = insertAfterIndex + 1;
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
   * Call the AI backend and stream the response using signal-based PromptModel.
   */
  private async _callAI(
    panel: NotebookPanel,
    prompt: string,
    context: IPromptContext,
    outputCell: Cell,
    model: string,
    kernelId: string | undefined
  ): Promise<void> {
    // Create or get a PromptModel for this execution
    const promptModel = new PromptModel();

    // Connect output changes to cell updates
    const onOutputChanged = (_: IPromptModel, output: string) => {
      if (!outputCell.isDisposed) {
        outputCell.model.sharedModel.setSource(output);
      }
    };
    promptModel.outputChanged.connect(onOutputChanged);

    // Abort on cell disposal
    const abortOnDispose = () => promptModel.abort();
    outputCell.disposed.connect(abortOnDispose);

    try {
      const maxSteps = this._settings?.maxToolSteps ?? 5;
      
      await promptModel.executePrompt(prompt, context, {
        model,
        kernelId,
        maxSteps
      });

      // Render markdown and add convert button
      if (!outputCell.isDisposed && outputCell instanceof MarkdownCell) {
        outputCell.rendered = true;
        const showButton = this._settings?.showConvertButton ?? true;
        if (showButton) {
          this._addConvertButton(panel, outputCell, promptModel.output);
        }
      }
    } catch (error: unknown) {
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
      promptModel.outputChanged.disconnect(onOutputChanged);
      outputCell.disposed.disconnect(abortOnDispose);
      (promptModel as PromptModel).dispose();
    }
  }

  /**
   * Check if a cell is a prompt cell.
   */
  isPromptCell(cell: Cell): boolean {
    return this._isPromptCellModel(cell.model);
  }

  /**
   * Check if a cell model is a prompt cell.
   */
  private _isPromptCellModel(model: ICellModel): boolean {
    const metadata = model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
    return metadata?.isPromptCell === true;
  }

  /**
   * Add a "Convert to Cells" button to an AI response cell.
   * Stores content in cell metadata and adds a persistent button.
   */
  private _addConvertButton(panel: NotebookPanel, cell: MarkdownCell, content: string): void {
    // Store content in metadata for later retrieval
    cell.model.setMetadata('ai_jup_content', content);
    
    // Check if button already exists
    const existingContainer = cell.node.querySelector('.ai-jup-convert-button-container');
    if (existingContainer) {
      return;
    }

    // Create button container - append directly to cell node
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'ai-jup-convert-button-container';

    const button = document.createElement('button');
    button.className = 'jp-mod-styled ai-jup-convert-button';
    button.innerHTML = '<span class="jp-ToolbarButtonComponent-icon"></span><span class="jp-ToolbarButtonComponent-label">Convert to Cells</span>';
    button.title = 'Convert this response into separate code and markdown cells';

    button.addEventListener('click', () => {
      const storedContent = cell.model.getMetadata('ai_jup_content') as string || content;
      this._convertToCells(panel, cell, storedContent);
    });

    buttonContainer.appendChild(button);

    // Append directly to cell node (most stable location)
    cell.node.appendChild(buttonContainer);
  }

  /**
   * Convert an AI response cell into native code and markdown cells.
   */
  private _convertToCells(panel: NotebookPanel, responseCell: Cell, content: string): void {
    const notebook = panel.content;
    const cellIndex = notebook.widgets.indexOf(responseCell);
    
    if (cellIndex < 0 || !notebook.model) {
      console.log('[ai-jup] Convert: invalid cell index or no model');
      return;
    }

    console.log('[ai-jup] Converting content:', content.substring(0, 200) + '...');

    // Parse the content into blocks
    const blocks = this._parseContentBlocks(content);
    
    console.log('[ai-jup] Parsed blocks:', blocks.length, blocks.map(b => ({ type: b.type, len: b.content.length })));
    
    if (blocks.length === 0) {
      console.log('[ai-jup] No blocks parsed, keeping original cell');
      return;
    }

    // Remove the response cell
    notebook.model.sharedModel.deleteCell(cellIndex);

    // Insert new cells in reverse order (so they end up in correct order)
    for (let i = blocks.length - 1; i >= 0; i--) {
      const block = blocks[i];
      const cellData = {
        cell_type: block.type === 'code' ? 'code' : 'markdown',
        source: block.content,
        metadata: {}
      };
      notebook.model.sharedModel.insertCell(cellIndex, cellData);
    }
    
    console.log('[ai-jup] Inserted', blocks.length, 'cells');
  }

  /**
   * Parse markdown content into code and text blocks.
   */
  private _parseContentBlocks(content: string): Array<{ type: 'code' | 'markdown'; content: string; language?: string }> {
    const blocks: Array<{ type: 'code' | 'markdown'; content: string; language?: string }> = [];
    
    // Normalize line endings
    const normalizedContent = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    
    // Regex to match fenced code blocks - handles:
    // - Optional language specifier
    // - Optional whitespace after language
    // - Code content (non-greedy)
    // - Closing ``` (may be preceded by newline or not)
    const codeBlockRegex = /```(\w*)[ \t]*\n?([\s\S]*?)\n?```/g;
    
    let lastIndex = 0;
    let match;

    console.log('[ai-jup] Parsing content, length:', normalizedContent.length);
    console.log('[ai-jup] Content starts with:', JSON.stringify(normalizedContent.substring(0, 100)));

    while ((match = codeBlockRegex.exec(normalizedContent)) !== null) {
      console.log('[ai-jup] Found code block match at', match.index, 'language:', match[1], 'code length:', match[2].length);
      
      // Add any text before this code block
      const textBefore = normalizedContent.slice(lastIndex, match.index).trim();
      if (textBefore) {
        blocks.push({ type: 'markdown', content: textBefore });
      }

      // Add the code block
      const language = match[1] || 'python';
      const code = match[2].trim();
      if (code) {
        blocks.push({ type: 'code', content: code, language });
      }

      lastIndex = match.index + match[0].length;
    }

    // Add any remaining text after the last code block
    const remainingText = normalizedContent.slice(lastIndex).trim();
    if (remainingText) {
      blocks.push({ type: 'markdown', content: remainingText });
    }

    // If no code blocks found but content exists, return as single markdown block
    if (blocks.length === 0 && normalizedContent.trim()) {
      console.log('[ai-jup] No code blocks found, returning as single markdown');
      blocks.push({ type: 'markdown', content: normalizedContent.trim() });
    }

    return blocks;
  }
}
