/**
 * AI-Jup E2E testing helpers.
 * 
 * These utilities centralize common patterns and reduce test brittleness
 * by providing semantic helpers instead of raw DOM/keyboard operations.
 */

import { expect, IJupyterLabPageFixture } from '@jupyterlab/galata';

export const PROMPT_CELL_CLASS = 'ai-jup-prompt-cell';

/**
 * Cell state information returned by getNotebookState.
 */
export interface CellState {
  index: number;
  type: 'code' | 'markdown' | 'raw';
  isPrompt: boolean;
  source: string;
  active: boolean;
  selected: boolean;
  classes: string[];
}

/**
 * Get the logical state of all cells in the current notebook.
 * Useful for debugging and making assertions about notebook state.
 */
export async function getNotebookState(page: IJupyterLabPageFixture): Promise<CellState[]> {
  return page.evaluate(() => {
    const app = (window as any).jupyterapp;
    const panel = app.shell.currentWidget;
    if (!panel || !panel.content) {
      return [];
    }
    const notebook = panel.content;
    return notebook.widgets.map((cell: any, index: number) => {
      const metadata = cell.model.getMetadata('ai_jup') || {};
      return {
        index,
        type: cell.model.type,
        isPrompt: metadata.isPromptCell === true,
        source: cell.model.sharedModel.getSource(),
        active: notebook.activeCellIndex === index,
        selected: notebook.isSelected(cell),
        classes: Array.from(cell.node.classList)
      };
    });
  });
}

/**
 * Dump notebook state to console for debugging.
 * Only use in failing tests or with DEBUG_AI_JUP env var.
 */
export async function dumpNotebookState(page: IJupyterLabPageFixture, label: string): Promise<void> {
  const state = await getNotebookState(page);
  console.log(`[ai-jup][${label}] Notebook state:`, JSON.stringify(state, null, 2));
}

/**
 * Wait for the kernel to reach idle status.
 * Replaces arbitrary waitForTimeout calls with semantic waiting.
 */
export async function waitForKernelIdle(page: IJupyterLabPageFixture, timeout = 10000): Promise<void> {
  await page.waitForFunction(
    () => {
      const app = (window as any).jupyterapp;
      const panel = app.shell.currentWidget;
      if (!panel || !panel.sessionContext) {
        return false;
      }
      const session = panel.sessionContext.session;
      return session?.kernel?.status === 'idle';
    },
    { timeout }
  );
}

/**
 * Wait for the kernel to be ready (connected and not starting).
 */
export async function waitForKernelReady(page: IJupyterLabPageFixture, timeout = 15000): Promise<void> {
  await page.waitForFunction(
    () => {
      const app = (window as any).jupyterapp;
      const panel = app.shell.currentWidget;
      if (!panel || !panel.sessionContext) {
        return false;
      }
      const session = panel.sessionContext.session;
      const status = session?.kernel?.status;
      return status === 'idle' || status === 'busy';
    },
    { timeout }
  );
}

/**
 * Execute a JupyterLab command by ID.
 * Useful when testing command behavior without relying on keybindings.
 */
export async function executeCommand(page: IJupyterLabPageFixture, command: string, args?: any): Promise<any> {
  return page.evaluate(
    ([cmd, a]) => (window as any).jupyterapp.commands.execute(cmd, a),
    [command, args] as const
  );
}

/**
 * Insert a prompt cell below the current cell using the command.
 */
export async function insertPromptCell(page: IJupyterLabPageFixture): Promise<void> {
  const countBefore = await page.locator(`.${PROMPT_CELL_CLASS}`).count();
  await executeCommand(page, 'ai-jup:insert-prompt-cell');
  await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(countBefore + 1, { timeout: 10000 });
}

/**
 * Insert a prompt cell using the keyboard shortcut (tests the keybinding path).
 */
export async function insertPromptCellViaKeyboard(page: IJupyterLabPageFixture): Promise<void> {
  const countBefore = await page.locator(`.${PROMPT_CELL_CLASS}`).count();
  await page.keyboard.press('Meta+Shift+p');
  await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(countBefore + 1, { timeout: 10000 });
}

/**
 * Wait for exactly N prompt cells to exist.
 */
export async function waitForPromptCells(page: IJupyterLabPageFixture, count: number, timeout = 10000): Promise<void> {
  await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(count, { timeout });
}

/**
 * Convert the currently active cell to a prompt via the dropdown.
 */
export async function convertToPromptViaDropdown(page: IJupyterLabPageFixture): Promise<void> {
  const countBefore = await page.locator(`.${PROMPT_CELL_CLASS}`).count();
  const dropdown = page.getByLabel('Cell type');
  await dropdown.selectOption('prompt');
  await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(countBefore + 1, { timeout: 5000 });
}

/**
 * Convert the currently active cell to a specific type via the dropdown.
 */
export async function convertCellTypeViaDropdown(
  page: IJupyterLabPageFixture, 
  cellType: 'code' | 'markdown' | 'raw' | 'prompt'
): Promise<void> {
  const dropdown = page.getByLabel('Cell type');
  await dropdown.selectOption(cellType);
  // Wait for the dropdown value to reflect the change
  await expect(dropdown).toHaveValue(cellType, { timeout: 5000 });
}

/**
 * Get the current dropdown value for cell type.
 */
export async function getCellTypeDropdownValue(page: IJupyterLabPageFixture): Promise<string> {
  const dropdown = page.getByLabel('Cell type');
  return dropdown.inputValue();
}

/**
 * Move to a cell by index using keyboard navigation from command mode.
 * Ensures the notebook is in command mode and waits for the UI to update.
 */
export async function navigateToCell(page: IJupyterLabPageFixture, targetIndex: number): Promise<void> {
  const currentState = await getNotebookState(page);
  const currentActive = currentState.findIndex(c => c.active);
  
  if (currentActive === targetIndex) {
    return;
  }
  
  // Ensure we're in command mode
  await page.keyboard.press('Escape');
  
  const diff = targetIndex - currentActive;
  const key = diff > 0 ? 'j' : 'k';
  const steps = Math.abs(diff);
  
  for (let i = 0; i < steps; i++) {
    await page.keyboard.press(key);
  }
  
  // Verify we reached the target and the cell is focused
  await page.waitForFunction(
    (idx) => {
      const app = (window as any).jupyterapp;
      const panel = app.shell.currentWidget;
      return panel?.content?.activeCellIndex === idx;
    },
    targetIndex,
    { timeout: 5000 }
  );
  
  // Click on the cell to ensure focus is properly set (triggers toolbar update)
  await page.locator(`.jp-Cell[data-windowed-list-index="${targetIndex}"]`).click();
  
  // Small wait for toolbar to update
  await page.waitForTimeout(100);
}

/**
 * Check if commands are registered in JupyterLab.
 */
export async function checkCommandsRegistered(
  page: IJupyterLabPageFixture, 
  commands: string[]
): Promise<Record<string, boolean>> {
  return page.evaluate((cmds) => {
    const app = (window as any).jupyterapp;
    if (!app || !app.commands) {
      return Object.fromEntries(cmds.map(c => [c, false]));
    }
    return Object.fromEntries(cmds.map(c => [c, app.commands.hasCommand(c)]));
  }, commands);
}

/**
 * Assert that a cell at a given index is a prompt cell.
 */
export async function assertCellIsPrompt(page: IJupyterLabPageFixture, index: number): Promise<void> {
  const state = await getNotebookState(page);
  expect(state[index]).toBeDefined();
  expect(state[index].isPrompt).toBe(true);
  expect(state[index].type).toBe('markdown');
}

/**
 * Assert that a cell at a given index is NOT a prompt cell.
 */
export async function assertCellIsNotPrompt(page: IJupyterLabPageFixture, index: number): Promise<void> {
  const state = await getNotebookState(page);
  expect(state[index]).toBeDefined();
  expect(state[index].isPrompt).toBe(false);
}

/**
 * Get the count of prompt cells based on metadata (more reliable than DOM classes).
 */
export async function getPromptCellCount(page: IJupyterLabPageFixture): Promise<number> {
  const state = await getNotebookState(page);
  return state.filter(c => c.isPrompt).length;
}

/**
 * Run the current cell and wait for execution to complete.
 * More reliable than checking for specific prompt text like "[1]".
 */
export async function runCellAndWait(page: IJupyterLabPageFixture, timeout = 10000): Promise<void> {
  await page.keyboard.press('Shift+Enter');
  await waitForKernelIdle(page, timeout);
}
