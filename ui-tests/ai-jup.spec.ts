/**
 * Galata E2E tests for ai-jup JupyterLab extension.
 * 
 * These tests verify the UI behavior of the extension in a real browser.
 * API-level functionality is tested separately in Python tests.
 */

import { expect, test } from '@jupyterlab/galata';
import {
  PROMPT_CELL_CLASS,
  insertPromptCell,
  insertPromptCellViaKeyboard,
  waitForPromptCells,
  waitForKernelReady,
  convertToPromptViaDropdown,
  convertCellTypeViaDropdown,
  getNotebookState,
  checkCommandsRegistered,
  assertCellIsPrompt,
  navigateToCell
} from './helpers';

test.describe('Extension Activation', () => {

  test('API endpoint returns valid models list', async ({ request, baseURL }) => {
    const response = await request.get(`${baseURL}/ai-jup/models`);
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(data.models).toBeDefined();
    expect(Array.isArray(data.models)).toBe(true);
    expect(data.models.length).toBeGreaterThan(0);
    
    // Verify model structure
    const firstModel = data.models[0];
    expect(firstModel).toHaveProperty('id');
    expect(firstModel).toHaveProperty('name');
  });
});

test.describe('Prompt Cell Creation', () => {
  
  test('keyboard shortcut creates prompt cell with correct structure', async ({ page }) => {
    await page.notebook.createNew();
    const cellCountBefore = await page.notebook.getCellCount();
    
    // Use keyboard shortcut to insert prompt cell
    await insertPromptCellViaKeyboard(page);
    
    // Verify cell count increased by exactly 1
    const cellCountAfter = await page.notebook.getCellCount();
    expect(cellCountAfter).toBe(cellCountBefore + 1);
    
    // Verify the new cell has the prompt class and marker
    const promptCell = page.locator(`.${PROMPT_CELL_CLASS}`);
    await expect(promptCell).toHaveCount(1);
    await expect(promptCell).toContainText('AI Prompt');
  });

  test('prompt cell is inserted below active cell', async ({ page }) => {
    await page.notebook.createNew();
    
    // Type content in first cell to identify it
    await page.keyboard.type('first_cell = 1');
    
    // Insert prompt below it
    await insertPromptCell(page);
    
    // Verify notebook state
    const state = await getNotebookState(page);
    expect(state).toHaveLength(2);
    
    // First cell should NOT be a prompt
    expect(state[0].isPrompt).toBe(false);
    expect(state[0].source).toContain('first_cell');
    
    // Second cell should be a prompt
    expect(state[1].isPrompt).toBe(true);
    expect(state[1].type).toBe('markdown');
  });
});

test.describe('Prompt Cell Metadata Persistence', () => {
  
  test('prompt cell metadata is saved to notebook file', async ({ page, request, baseURL, tmpPath }) => {
    const fileName = 'metadata-test.ipynb';
    
    await page.notebook.createNew(fileName);
    await insertPromptCell(page);
    
    // Type unique content we can verify
    const uniqueContent = `Test prompt ${Date.now()}`;
    await page.keyboard.type(uniqueContent);
    
    await page.notebook.save();
    // Wait for save indicator to clear
    await expect(page.locator('.jp-mod-dirty')).toHaveCount(0, { timeout: 5000 });
    
    // Read notebook via API and verify metadata
    const response = await request.get(`${baseURL}/api/contents/${tmpPath}/${fileName}?content=1`);
    expect(response.ok()).toBeTruthy();
    
    const contents = await response.json();
    const notebook = contents.content;
    
    // Find the prompt cell and verify its metadata
    const promptCells = notebook.cells.filter((cell: any) => 
      cell.metadata?.ai_jup?.isPromptCell === true
    );
    
    expect(promptCells.length).toBe(1);
    expect(promptCells[0].metadata.ai_jup.model).toBeDefined();
    
    // Verify the content was saved
    const source = Array.isArray(promptCells[0].source) 
      ? promptCells[0].source.join('') 
      : promptCells[0].source;
    expect(source).toContain(uniqueContent);
  });
});

test.describe('Command Registration', () => {
  
  test('ai-jup commands are available via app.commands', async ({ page }) => {
    await page.notebook.createNew();
    
    const commands = await checkCommandsRegistered(page, [
      'ai-jup:insert-prompt-cell',
      'ai-jup:run-prompt'
    ]);
    
    expect(commands['ai-jup:insert-prompt-cell']).toBe(true);
    expect(commands['ai-jup:run-prompt']).toBe(true);
  });

  test('insert command creates prompt cell', async ({ page }) => {
    await page.notebook.createNew();
    
    // Use the command directly (tests command registration, not keybinding)
    await insertPromptCell(page);
    
    // Verify prompt cell was created
    await waitForPromptCells(page, 1);
  });
});

test.describe('Multiple Prompt Cells', () => {
  
  test('can create multiple independent prompt cells', async ({ page }) => {
    await page.notebook.createNew();
    
    // Insert first prompt
    await insertPromptCell(page);
    await page.keyboard.type('First prompt content');
    
    // Verify first prompt exists before inserting second
    await waitForPromptCells(page, 1);
    
    // Insert second prompt
    await insertPromptCell(page);
    await page.keyboard.type('Second prompt content');
    
    // Verify exactly 2 prompt cells exist
    await waitForPromptCells(page, 2);
    
    // Verify both have expected content (order-independent)
    const state = await getNotebookState(page);
    const promptSources = state.filter(c => c.isPrompt).map(c => c.source);
    expect(promptSources.some(s => s.includes('First prompt'))).toBe(true);
    expect(promptSources.some(s => s.includes('Second prompt'))).toBe(true);
  });
});

test.describe('Prompt Cell Editing', () => {
  
  test('prompt cell content is editable', async ({ page }) => {
    await page.notebook.createNew();
    await insertPromptCell(page);
    
    // Type content
    const originalContent = 'Original text';
    await page.keyboard.type(originalContent);
    
    // Verify original content
    const promptCell = page.locator(`.${PROMPT_CELL_CLASS}`);
    await expect(promptCell).toContainText(originalContent);
    
    // Edit: select all and replace
    await page.keyboard.press('Meta+a');
    const newContent = 'Completely new text';
    await page.keyboard.type(newContent);
    
    // Verify new content replaced old
    await expect(promptCell).toContainText(newContent);
    await expect(promptCell).not.toContainText(originalContent);
  });

  test('prompt cell can be deleted', async ({ page }) => {
    await page.notebook.createNew();
    await insertPromptCell(page);
    
    // Verify prompt exists
    await waitForPromptCells(page, 1);
    
    // Select and delete the prompt cell
    await page.locator(`.${PROMPT_CELL_CLASS}`).first().click();
    await page.keyboard.press('Escape'); // Command mode
    await page.keyboard.press('d');
    await page.keyboard.press('d'); // Delete cell
    
    // Verify prompt cell is gone
    await waitForPromptCells(page, 0);
  });
});

test.describe('Kernel Integration', () => {
  
  test('prompt cell can be created in fresh notebook', async ({ page }) => {
    await page.notebook.createNew();
    
    // Wait for kernel to be ready
    await waitForKernelReady(page);
    
    // Insert prompt cell - should work with fresh kernel
    await insertPromptCell(page);
    
    // Verify prompt cell was created successfully
    await waitForPromptCells(page, 1);
    
    // Verify the AI Prompt marker is present
    const promptCell = page.locator(`.${PROMPT_CELL_CLASS}`);
    await expect(promptCell).toContainText('AI Prompt');
  });
});

test.describe('Cell Type Dropdown', () => {
  
  test('dropdown shows Prompt option', async ({ page }) => {
    await page.notebook.createNew();
    
    // Get the cell type dropdown
    const dropdown = page.getByLabel('Cell type');
    await expect(dropdown).toBeVisible();
    
    // Check that it has the Prompt option
    const options = await dropdown.locator('option').allTextContents();
    expect(options).toContain('Prompt');
    expect(options).toContain('Code');
    expect(options).toContain('Markdown');
    expect(options).toContain('Raw');
  });

  test('selecting Prompt from dropdown converts cell to prompt type', async ({ page }) => {
    await page.notebook.createNew();
    
    // Initially should be a code cell
    const dropdown = page.getByLabel('Cell type');
    await expect(dropdown).toHaveValue('code');
    
    // Convert to prompt via dropdown
    await convertToPromptViaDropdown(page);
    
    // Verify it became a prompt cell
    await waitForPromptCells(page, 1);
    await expect(dropdown).toHaveValue('prompt');
  });

  test('selecting Code from Prompt dropdown converts back to code cell', async ({ page }) => {
    await page.notebook.createNew();
    
    // Convert to prompt first
    await convertToPromptViaDropdown(page);
    await waitForPromptCells(page, 1);
    
    // Convert back to code
    await convertCellTypeViaDropdown(page, 'code');
    
    // Verify prompt class is removed
    await waitForPromptCells(page, 0);
    
    // Verify it's a code cell via metadata
    const state = await getNotebookState(page);
    expect(state[0].type).toBe('code');
    expect(state[0].isPrompt).toBe(false);
  });

  test('dropdown shows correct value when selecting different cells', async ({ page }) => {
    await page.notebook.createNew();
    const dropdown = page.getByLabel('Cell type');
    
    // First cell is code
    await expect(dropdown).toHaveValue('code');
    
    // Insert a new cell below (using keyboard in command mode)
    await page.keyboard.press('Escape'); // Ensure command mode
    await page.keyboard.press('b'); // Insert cell below
    
    // The new cell should be active and be a code cell
    await expect(dropdown).toHaveValue('code');
    
    // Convert the new cell (cell 1) to prompt
    await convertToPromptViaDropdown(page);
    await expect(dropdown).toHaveValue('prompt');
    
    // Verify we have the right state: cell 0 = code, cell 1 = prompt
    const stateBefore = await getNotebookState(page);
    expect(stateBefore[0].type).toBe('code');
    expect(stateBefore[0].isPrompt).toBe(false);
    expect(stateBefore[1].isPrompt).toBe(true);
    
    // Navigate back to first cell using keyboard
    await page.keyboard.press('Escape');
    await page.keyboard.press('k'); // Move up
    await expect(dropdown).toHaveValue('code', { timeout: 5000 });
    
    // Navigate to second cell
    await page.keyboard.press('j'); // Move down
    await expect(dropdown).toHaveValue('prompt', { timeout: 5000 });
  });

  test('dropdown preserves cell content when converting to prompt', async ({ page }) => {
    await page.notebook.createNew();
    
    // Add content to code cell
    const content = 'my_content = 42';
    await page.keyboard.type(content);
    
    // Convert to prompt
    await convertToPromptViaDropdown(page);
    
    // Verify content is preserved
    const promptCell = page.locator(`.${PROMPT_CELL_CLASS}`);
    await expect(promptCell).toContainText(content);
  });

  test('dropdown preserves cell content when converting from prompt', async ({ page }) => {
    await page.notebook.createNew();
    
    // Convert to prompt and wait for it
    await convertToPromptViaDropdown(page);
    await waitForPromptCells(page, 1);
    
    // Click into the prompt cell to enter edit mode
    await page.locator(`.${PROMPT_CELL_CLASS}`).click();
    
    // Type content after the AI Prompt prefix
    const content = 'my prompt content here';
    await page.keyboard.type(content);
    
    // Verify content was typed
    await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toContainText(content);
    
    // Convert to code
    await convertCellTypeViaDropdown(page, 'code');
    
    // Verify content is preserved (includes both prefix and typed content)
    const codeCell = page.locator('.jp-CodeCell');
    await expect(codeCell).toContainText(content);
  });

  test('prompt cell metadata is saved to notebook file via dropdown', async ({ page, request, baseURL, tmpPath }) => {
    const fileName = 'dropdown-metadata-test.ipynb';
    
    await page.notebook.createNew(fileName);
    
    // Convert to prompt via dropdown
    await convertToPromptViaDropdown(page);
    await waitForPromptCells(page, 1);
    
    // Type content
    const uniqueContent = `Dropdown prompt ${Date.now()}`;
    await page.keyboard.type(uniqueContent);
    
    // Save
    await page.notebook.save();
    await expect(page.locator('.jp-mod-dirty')).toHaveCount(0, { timeout: 5000 });
    
    // Verify metadata in saved file
    const response = await request.get(`${baseURL}/api/contents/${tmpPath}/${fileName}?content=1`);
    const contents = await response.json();
    
    const promptCells = contents.content.cells.filter((cell: any) => 
      cell.metadata?.ai_jup?.isPromptCell === true
    );
    
    expect(promptCells.length).toBe(1);
    expect(promptCells[0].cell_type).toBe('markdown');
    expect(promptCells[0].metadata.ai_jup.model).toBeDefined();
  });
});

test.describe('Variable and Function Syntax', () => {
  
  test('$variable syntax is preserved in saved notebook', async ({ page, request, baseURL, tmpPath }) => {
    const fileName = 'var-syntax-test.ipynb';
    
    await page.notebook.createNew(fileName);
    
    // Define a variable in kernel
    await page.keyboard.type('my_variable = 123');
    await page.keyboard.press('Shift+Enter');
    
    // Wait for execution (kernel becomes idle after execution)
    await waitForKernelReady(page);
    
    // Insert prompt with $variable syntax
    await insertPromptCell(page);
    await page.keyboard.type('The value of $my_variable is important');
    
    // Save notebook
    await page.notebook.save();
    await expect(page.locator('.jp-mod-dirty')).toHaveCount(0, { timeout: 5000 });
    
    // Verify the $variable syntax is preserved in the saved file
    const response = await request.get(`${baseURL}/api/contents/${tmpPath}/${fileName}?content=1`);
    const contents = await response.json();
    
    const promptCell = contents.content.cells.find((c: any) => c.metadata?.ai_jup?.isPromptCell);
    expect(promptCell).toBeDefined();
    
    const source = Array.isArray(promptCell.source) ? promptCell.source.join('') : promptCell.source;
    expect(source).toContain('$my_variable');
  });

  test('&function syntax is preserved in saved notebook', async ({ page, request, baseURL, tmpPath }) => {
    const fileName = 'func-syntax-test.ipynb';
    
    await page.notebook.createNew(fileName);
    
    // Define a function in kernel
    await page.keyboard.type('def my_function(x):\n    return x * 2');
    await page.keyboard.press('Shift+Enter');
    
    // Wait for execution
    await waitForKernelReady(page);
    
    // Insert prompt with &function syntax
    await insertPromptCell(page);
    await page.keyboard.type('Use &my_function to double the value');
    
    // Save notebook
    await page.notebook.save();
    await expect(page.locator('.jp-mod-dirty')).toHaveCount(0, { timeout: 5000 });
    
    // Verify the &function syntax is preserved
    const response = await request.get(`${baseURL}/api/contents/${tmpPath}/${fileName}?content=1`);
    const contents = await response.json();
    
    const promptCell = contents.content.cells.find((c: any) => c.metadata?.ai_jup?.isPromptCell);
    expect(promptCell).toBeDefined();
    
    const source = Array.isArray(promptCell.source) ? promptCell.source.join('') : promptCell.source;
    expect(source).toContain('&my_function');
  });
});
