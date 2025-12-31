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
import { ICommandPalette } from '@jupyterlab/apputils';
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
  optional: [ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    notebookTracker: INotebookTracker,
    palette: ICommandPalette | null
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

    app.commands.addKeyBinding({
      command: runPromptCommand,
      keys: ['Accel Shift Enter'],
      selector: '.jp-Notebook .jp-Cell.ai-jup-prompt-cell'
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

    // Helper to set up a notebook panel
    const setupPanel = (panel: NotebookPanel) => {
      const doSetup = () => {
        // Skip if notebook was closed before context became ready
        if (panel.isDisposed) {
          return;
        }
        const connector = new KernelConnector(panel.sessionContext);
        promptCellManager.setupNotebook(panel, connector);
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
