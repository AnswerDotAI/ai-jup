/**
 * Custom cell type switcher that adds "Prompt" option to the dropdown.
 * 
 * Replaces the default JupyterLab cell type switcher via IToolbarWidgetRegistry.
 */

import * as React from 'react';
import { ReactWidget } from '@jupyterlab/ui-components';
import { NotebookPanel, NotebookActions, Notebook } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import * as nbformat from '@jupyterlab/nbformat';
import type { IPromptCellManager } from './tokens';

const TOOLBAR_CELLTYPE_CLASS = 'jp-Notebook-toolbarCellType';
const TOOLBAR_CELLTYPE_DROPDOWN_CLASS = 'jp-Notebook-toolbarCellTypeDropdown';
const PROMPT_METADATA_KEY = 'ai_jup';
const PROMPT_CELL_CLASS = 'ai-jup-prompt-cell';

interface PromptMetadata {
  isPromptCell: boolean;
  model?: string;
}

/**
 * Extended cell type that includes 'prompt'.
 */
type ExtendedCellType = nbformat.CellType | 'prompt';

/**
 * Custom cell type switcher widget with Prompt option.
 */
export class CustomCellTypeSwitcher extends ReactWidget {
  private _notebook: Notebook;
  private _trans: ReturnType<ITranslator['load']>;

  constructor(
    panel: NotebookPanel,
    _promptCellManager: IPromptCellManager,
    translator?: ITranslator
  ) {
    super();
    this._trans = (translator ?? nullTranslator).load('jupyterlab');
    this.addClass(TOOLBAR_CELLTYPE_CLASS);
    this._notebook = panel.content;

    if (this._notebook.model) {
      this.update();
    }
    this._notebook.activeCellChanged.connect(this.update, this);
    this._notebook.selectionChanged.connect(this.update, this);

    // Clean up on dispose
    panel.disposed.connect(() => {
      this._notebook.activeCellChanged.disconnect(this.update, this);
      this._notebook.selectionChanged.disconnect(this.update, this);
    });
  }

  /**
   * Handle cell type change from dropdown.
   */
  handleChange = (event: React.ChangeEvent<HTMLSelectElement>): void => {
    const newType = event.target.value as ExtendedCellType;
    if (newType === '-') {
      return;
    }

    if (newType === 'prompt') {
      this._convertToPrompt();
    } else {
      // Remove prompt metadata if converting away from prompt
      this._removePromptMetadata();
      NotebookActions.changeCellType(this._notebook, newType as nbformat.CellType);
    }
    this._notebook.activate();
  };

  /**
   * Handle keyboard navigation.
   */
  handleKeyDown = (event: React.KeyboardEvent): void => {
    if (event.key === 'Enter') {
      this._notebook.activate();
    }
  };

  /**
   * Convert selected cells to prompt type.
   */
  private _convertToPrompt(): void {
    const notebook = this._notebook;
    if (!notebook.model) {
      return;
    }

    // Collect indices of cells to convert (don't modify during iteration)
    const indicesToConvert: number[] = [];
    notebook.widgets.forEach((cell, index) => {
      if (!notebook.isSelectedOrActive(cell)) {
        return;
      }
      // Check if already a prompt cell
      const metadata = cell.model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
      if (metadata?.isPromptCell) {
        return;
      }
      indicesToConvert.push(index);
    });

    // Convert cells (process in reverse to preserve indices)
    for (let i = indicesToConvert.length - 1; i >= 0; i--) {
      const index = indicesToConvert[i];
      const cell = notebook.widgets[index];
      if (!cell) continue;

      const needsTypeChange = cell.model.type !== 'markdown';
      
      // First change the cell type if needed (using NotebookActions for proper handling)
      if (needsTypeChange) {
        // Make this cell the active cell for NotebookActions
        notebook.activeCellIndex = index;
        notebook.deselectAll();
        NotebookActions.changeCellType(notebook, 'markdown');
      }
      
      // Now set the prompt metadata on the (possibly new) cell
      const targetCell = notebook.widgets[index];
      if (targetCell) {
        targetCell.model.setMetadata(PROMPT_METADATA_KEY, {
          isPromptCell: true,
          model: 'claude-sonnet-4-20250514'
        } as PromptMetadata);
        
        // Add prompt prefix if source is empty
        const source = targetCell.model.sharedModel.getSource();
        if (!source || !source.trim()) {
          targetCell.model.sharedModel.setSource('**AI Prompt:** ');
        }
        
        // Add styling class
        if (!targetCell.hasClass(PROMPT_CELL_CLASS)) {
          targetCell.addClass(PROMPT_CELL_CLASS);
        }
      }
    }

    notebook.deselectAll();
  }

  /**
   * Remove prompt metadata from selected cells.
   */
  private _removePromptMetadata(): void {
    const notebook = this._notebook;
    
    notebook.widgets.forEach((cell) => {
      if (!notebook.isSelectedOrActive(cell)) {
        return;
      }

      // Remove prompt metadata
      const metadata = cell.model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
      if (metadata?.isPromptCell) {
        cell.model.deleteMetadata(PROMPT_METADATA_KEY);
        cell.removeClass(PROMPT_CELL_CLASS);
      }
    });
  }

  /**
   * Get the current cell type value for the dropdown.
   */
  private _getValue(): ExtendedCellType | '-' {
    const notebook = this._notebook;
    
    if (!notebook.activeCell) {
      return '-';
    }

    // Check if active cell is a prompt cell
    let value: ExtendedCellType | '-' = this._isPromptCell(notebook.activeCell.model) 
      ? 'prompt' 
      : notebook.activeCell.model.type;

    // Check all selected cells for consistency
    for (const widget of notebook.widgets) {
      if (notebook.isSelectedOrActive(widget)) {
        const cellType = this._isPromptCell(widget.model) ? 'prompt' : widget.model.type;
        if (cellType !== value) {
          return '-';
        }
      }
    }

    return value;
  }

  /**
   * Check if a cell model is a prompt cell.
   */
  private _isPromptCell(model: { getMetadata: (key: string) => unknown }): boolean {
    const metadata = model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
    return metadata?.isPromptCell === true;
  }

  render(): JSX.Element {
    const value = this._getValue();

    return (
      <select
        className={TOOLBAR_CELLTYPE_DROPDOWN_CLASS}
        onChange={this.handleChange}
        onKeyDown={this.handleKeyDown}
        value={value}
        aria-label={this._trans.__('Cell type')}
        title={this._trans.__('Select the cell type')}
      >
        <option value="-">-</option>
        <option value="code">{this._trans.__('Code')}</option>
        <option value="markdown">{this._trans.__('Markdown')}</option>
        <option value="raw">{this._trans.__('Raw')}</option>
        <option value="prompt">{this._trans.__('Prompt')}</option>
      </select>
    );
  }
}
