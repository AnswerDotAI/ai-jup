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

import { INotebookTracker, NotebookPanel, INotebookWidgetFactory, NotebookWidgetFactory } from '@jupyterlab/notebook';
import { ICommandPalette, ToolbarButton, IToolbarWidgetRegistry } from '@jupyterlab/apputils';
import { IMainMenu } from '@jupyterlab/mainmenu';
import { ISettingRegistry } from '@jupyterlab/settingregistry';
import { ITranslator } from '@jupyterlab/translation';
import { addIcon } from '@jupyterlab/ui-components';
import { PromptCellManager } from './promptCell';
import { KernelConnector } from './kernelConnector';
import { SettingsManager } from './settings';
import { CustomCellTypeSwitcher } from './cellTypeSwitcher';
import {
  IPromptCellManager,
  IExtensionSettings,
  IKernelConnectorFactory
} from './tokens';

const PLUGIN_ID = 'ai-jup:plugin';

/**
 * Settings plugin that provides IExtensionSettings.
 */
const settingsPlugin: JupyterFrontEndPlugin<IExtensionSettings> = {
  id: 'ai-jup:settings',
  description: 'Provides AI-Jup extension settings',
  autoStart: true,
  requires: [],
  optional: [ISettingRegistry],
  provides: IExtensionSettings,
  activate: async (
    app: JupyterFrontEnd,
    settingRegistry: ISettingRegistry | null
  ): Promise<IExtensionSettings> => {
    const settingsManager = new SettingsManager();
    
    if (settingRegistry) {
      await settingsManager.initialize(settingRegistry);
      console.log('[ai-jup] Settings loaded:', settingsManager.toJSON());
    } else {
      console.log('[ai-jup] No setting registry available, using defaults');
    }
    
    return settingsManager;
  }
};

/**
 * Kernel connector factory plugin.
 */
const kernelConnectorPlugin: JupyterFrontEndPlugin<IKernelConnectorFactory> = {
  id: 'ai-jup:kernel-connector',
  description: 'Provides kernel connector factory',
  autoStart: true,
  provides: IKernelConnectorFactory,
  activate: (): IKernelConnectorFactory => {
    return {
      create: (sessionContext: unknown) => new KernelConnector(sessionContext as import('@jupyterlab/apputils').ISessionContext)
    };
  }
};

/**
 * Prompt cell manager plugin.
 */
const promptCellManagerPlugin: JupyterFrontEndPlugin<IPromptCellManager> = {
  id: 'ai-jup:prompt-cell-manager',
  description: 'Manages AI prompt cells',
  autoStart: true,
  requires: [IExtensionSettings],
  provides: IPromptCellManager,
  activate: (
    app: JupyterFrontEnd,
    settings: IExtensionSettings
  ): IPromptCellManager => {
    const manager = new PromptCellManager();
    manager.setSettings(settings);
    return manager;
  }
};

/**
 * Main plugin that sets up commands and UI.
 */
const mainPlugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  description: 'AI-powered prompt cells for JupyterLab',
  autoStart: true,
  requires: [INotebookTracker, IPromptCellManager, IKernelConnectorFactory],
  optional: [ICommandPalette, IMainMenu],
  activate: (
    app: JupyterFrontEnd,
    notebookTracker: INotebookTracker,
    promptCellManager: IPromptCellManager,
    connectorFactory: IKernelConnectorFactory,
    palette: ICommandPalette | null,
    mainMenu: IMainMenu | null
  ) => {
    console.log('AI-Jup extension activated');

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
          const connector = connectorFactory.create(panel.sessionContext);
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

/**
 * Plugin that replaces the cell type dropdown with one that includes "Prompt".
 */
const cellTypeSwitcherPlugin: JupyterFrontEndPlugin<void> = {
  id: 'ai-jup:cell-type-switcher',
  description: 'Adds Prompt option to cell type dropdown',
  autoStart: true,
  requires: [IToolbarWidgetRegistry, IPromptCellManager, INotebookWidgetFactory],
  optional: [ITranslator],
  activate: (
    app: JupyterFrontEnd,
    toolbarRegistry: IToolbarWidgetRegistry,
    promptCellManager: IPromptCellManager,
    _notebookWidgetFactory: NotebookWidgetFactory.IFactory,
    translator: ITranslator | null
  ) => {
    console.log('[ai-jup] Registering custom cell type switcher (after notebook widget factory)');
    
    const oldFactory = toolbarRegistry.addFactory<NotebookPanel>(
      'Notebook',
      'cellType',
      (panel: NotebookPanel) => {
        console.log('[ai-jup] Creating CustomCellTypeSwitcher for panel:', panel.id);
        return new CustomCellTypeSwitcher(panel, promptCellManager, translator ?? undefined);
      }
    );
    
    console.log('[ai-jup] Replaced cellType factory, old factory was:', oldFactory ? 'present' : 'none');
  }
};

export default [settingsPlugin, kernelConnectorPlugin, promptCellManagerPlugin, cellTypeSwitcherPlugin, mainPlugin];
