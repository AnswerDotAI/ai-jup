/**
 * AI-powered Jupyter Lab extension with prompt cells.
 * 
 * Features:
 * - $variable syntax to reference kernel variables in prompts
 * - &function syntax to give AI access to kernel functions as tools
 * - Prompt cells that see all preceding cells and kernel state
 */

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { ICommandPalette, ToolbarButton } from '@jupyterlab/apputils';
import { IMainMenu } from '@jupyterlab/mainmenu';
import { addIcon } from '@jupyterlab/ui-components';
import { PromptCellManager } from './promptCell';
import { KernelConnector } from './kernelConnector';

const PLUGIN_ID = 'ai-jup:plugin';

/**
 * Initialization data for the ai-jup extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  description: 'AI-powered prompt cells for JupyterLab',
  autoStart: true,
  requires: [INotebookTracker],
  optional: [ICommandPalette, IMainMenu],
  activate: (
    app: JupyterFrontEnd,
    notebookTracker: INotebookTracker,
    palette: ICommandPalette | null,
    mainMenu: IMainMenu | null
  ) => {
    console.log('AI-Jup extension activated');

    const promptCellManager = new PromptCellManager();

    // Command to insert a new prompt cell
    const insertPromptCommand = 'ai-jup:insert-prompt-cell';
    app.commands.addCommand(insertPromptCommand, {
      label: 'Insert AI Prompt Cell',
      caption: 'Insert a new AI prompt cell below the current cell',
      execute: () => {
        const panel = notebookTracker.currentWidget;
        if (!panel) {
          return;
        }
        promptCellManager.insertPromptCell(panel);
      }
    });

    // Command to run prompt cell
    const runPromptCommand = 'ai-jup:run-prompt';
    app.commands.addCommand(runPromptCommand, {
      label: 'Run AI Prompt',
      caption: 'Execute the current prompt cell',
      execute: async () => {
        const panel = notebookTracker.currentWidget;
        if (!panel) {
          return;
        }
        await promptCellManager.executePromptCell(panel);
      }
    });

    // Add keyboard shortcuts
    app.commands.addKeyBinding({
      command: insertPromptCommand,
      keys: ['Accel Shift P'],
      selector: '.jp-Notebook'
    });

    // "P" in command mode inserts prompt cell (like "M" for markdown, "Y" for code)
    app.commands.addKeyBinding({
      command: insertPromptCommand,
      keys: ['P'],
      selector: '.jp-Notebook.jp-mod-commandMode:not(.jp-mod-readWrite) :focus'
    });

    // Shift+Enter on prompt cells runs AI instead of normal execution
    app.commands.addKeyBinding({
      command: runPromptCommand,
      keys: ['Shift Enter'],
      selector: '.jp-Notebook.jp-mod-editMode .jp-Cell.ai-jup-prompt-cell'
    });

    app.commands.addKeyBinding({
      command: runPromptCommand,
      keys: ['Shift Enter'],
      selector: '.jp-Notebook.jp-mod-commandMode .jp-Cell.jp-mod-selected.ai-jup-prompt-cell'
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: insertPromptCommand,
        category: 'AI'
      });
      palette.addItem({
        command: runPromptCommand,
        category: 'AI'
      });
    }

    // Add to Edit menu
    if (mainMenu) {
      mainMenu.editMenu.addGroup([
        { command: insertPromptCommand },
        { command: runPromptCommand }
      ], 20);
    }

    // Helper to set up a notebook panel
    const setupPanel = (panel: NotebookPanel) => {
      const doSetup = () => {
        // Skip if notebook was closed before context became ready
        if (panel.isDisposed) {
          return;
        }
        
        // Add toolbar button for inserting prompt cells
        const button = new ToolbarButton({
          icon: addIcon,
          onClick: () => {
            promptCellManager.insertPromptCell(panel);
          },
          tooltip: 'Insert AI Prompt Cell (Cmd/Ctrl+Shift+P)',
          label: 'AI Prompt'
        });
        panel.toolbar.insertAfter('cellType', 'ai-jup-insert', button);
        
        // Use requestAnimationFrame to wait for cells to be rendered
        requestAnimationFrame(() => {
          if (panel.isDisposed) {
            return;
          }
          const connector = new KernelConnector(panel.sessionContext);
          promptCellManager.setupNotebook(panel, connector);
        });
      };
      if (panel.context.isReady) {
        doSetup();
      } else {
        panel.context.ready.then(doSetup);
      }
    };

    // Track new notebooks
    notebookTracker.widgetAdded.connect((_, panel) => setupPanel(panel));

    // Process existing notebooks
    notebookTracker.forEach(setupPanel);
  }
};

export default plugin;
