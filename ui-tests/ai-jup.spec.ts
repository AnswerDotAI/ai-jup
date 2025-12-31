/**
 * Galata E2E tests for ai-jup JupyterLab extension.
 * 
 * These tests verify the UI behavior of the extension in a real browser.
 * API-level functionality is tested separately in Python tests.
 */

import { expect, test, IJupyterLabPageFixture } from '@jupyterlab/galata';

const PROMPT_CELL_CLASS = 'ai-jup-prompt-cell';

// Helper to insert a prompt cell and wait for it
async function insertPromptCell(page: IJupyterLabPageFixture): Promise<void> {
  const countBefore = await page.locator(`.${PROMPT_CELL_CLASS}`).count();
  await page.keyboard.press('Meta+Shift+p');
  // Wait until a new prompt cell appears
  await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(countBefore + 1, { timeout: 10000 });
}

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
    
    await page.notebook.selectCells(0);
    await insertPromptCell(page);
    
    // Verify cell count increased by exactly 1
    const cellCountAfter = await page.notebook.getCellCount();
    expect(cellCountAfter).toBe(cellCountBefore + 1);
    
    // Verify the new cell has the prompt class
    const promptCell = page.locator(`.${PROMPT_CELL_CLASS}`);
    await expect(promptCell).toHaveCount(1);
    
    // Verify it contains the AI Prompt marker
    await expect(promptCell).toContainText('AI Prompt');
  });

  test('prompt cell is inserted below active cell', async ({ page }) => {
    await page.notebook.createNew();
    
    // Set content in first cell
    await page.notebook.setCell(0, 'code', 'first_cell = 1');
    
    // Select first cell and insert prompt below it
    await page.notebook.selectCells(0);
    await insertPromptCell(page);
    
    // Should now have 2 cells: original + prompt
    const cells = await page.notebook.getCellCount();
    expect(cells).toBe(2);
    
    // The prompt cell should be below the first cell (index 1)
    const secondCellClasses = await page.locator('.jp-Cell').nth(1).getAttribute('class');
    expect(secondCellClasses).toContain(PROMPT_CELL_CLASS);
    
    // First cell should NOT be a prompt cell
    const firstCellClasses = await page.locator('.jp-Cell').nth(0).getAttribute('class');
    expect(firstCellClasses).not.toContain(PROMPT_CELL_CLASS);
  });
});

test.describe('Prompt Cell Metadata Persistence', () => {
  
  test('prompt cell metadata is saved to notebook file', async ({ page, request, baseURL, tmpPath }) => {
    const fileName = 'metadata-test.ipynb';
    
    await page.notebook.createNew(fileName);
    await page.notebook.selectCells(0);
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
    
    // Execute the insert command directly via JupyterLab's command system
    // This is more reliable than testing the command palette UI
    const result = await page.evaluate(async () => {
      const app = (window as any).jupyterapp;
      if (!app || !app.commands) return { hasInsert: false, hasRun: false };
      
      return {
        hasInsert: app.commands.hasCommand('ai-jup:insert-prompt-cell'),
        hasRun: app.commands.hasCommand('ai-jup:run-prompt')
      };
    });
    
    expect(result.hasInsert).toBe(true);
    expect(result.hasRun).toBe(true);
  });

  test('insert command creates prompt cell', async ({ page }) => {
    await page.notebook.createNew();
    await page.notebook.selectCells(0);
    
    // Execute command directly
    await page.evaluate(async () => {
      const app = (window as any).jupyterapp;
      await app.commands.execute('ai-jup:insert-prompt-cell');
    });
    
    // Verify prompt cell was created
    await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(1, { timeout: 10000 });
  });
});

test.describe('Multiple Prompt Cells', () => {
  
  test('can create multiple independent prompt cells', async ({ page }) => {
    await page.notebook.createNew();
    await page.notebook.selectCells(0);
    
    // Insert first prompt
    await insertPromptCell(page);
    await page.keyboard.type('First prompt content');
    
    // Verify first prompt exists before inserting second
    await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(1);
    
    // Insert second prompt
    await insertPromptCell(page);
    await page.keyboard.type('Second prompt content');
    
    // Verify exactly 2 prompt cells exist
    const promptCells = page.locator(`.${PROMPT_CELL_CLASS}`);
    await expect(promptCells).toHaveCount(2);
    
    // Verify each has expected content (use textContent assertions)
    await expect(promptCells.first()).toContainText('First prompt');
    await expect(promptCells.nth(1)).toContainText('Second prompt');
  });
});

test.describe('Prompt Cell Editing', () => {
  
  test('prompt cell content is editable', async ({ page }) => {
    await page.notebook.createNew();
    await page.notebook.selectCells(0);
    await insertPromptCell(page);
    
    // Type content
    const originalContent = 'Original text';
    await page.keyboard.type(originalContent);
    
    // Verify original content
    let promptCell = page.locator(`.${PROMPT_CELL_CLASS}`);
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
    await page.notebook.selectCells(0);
    await insertPromptCell(page);
    
    // Verify prompt exists
    await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(1);
    
    // Select and delete the prompt cell
    await page.locator(`.${PROMPT_CELL_CLASS}`).first().click();
    await page.keyboard.press('Escape'); // Command mode
    await page.keyboard.press('d');
    await page.keyboard.press('d'); // Delete cell
    
    // Verify prompt cell is gone
    await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(0, { timeout: 5000 });
  });
});

test.describe('Kernel Integration', () => {
  
  test('prompt cell works after kernel restart', async ({ page }) => {
    await page.notebook.createNew();
    
    // Start the kernel by running a cell
    await page.notebook.setCell(0, 'code', 'x = 42');
    await page.notebook.runCell(0);
    
    // Wait for execution to complete
    await expect(page.locator('.jp-InputArea-prompt:has-text("[1]")')).toBeVisible({ timeout: 10000 });
    
    // Restart kernel
    await page.menu.clickMenuItem('Kernel>Restart Kernel…');
    const restartButton = page.locator('button:has-text("Restart")');
    await expect(restartButton).toBeVisible({ timeout: 5000 });
    await restartButton.click();
    
    // Wait for kernel to restart (status indicator changes)
    await page.waitForTimeout(2000);
    
    // Insert prompt cell - should work with fresh kernel
    await page.notebook.selectCells(0);
    await insertPromptCell(page);
    
    // Verify prompt cell was created successfully
    await expect(page.locator(`.${PROMPT_CELL_CLASS}`)).toHaveCount(1);
  });
});

test.describe('Variable and Function Syntax', () => {
  
  test('$variable syntax is preserved in saved notebook', async ({ page, request, baseURL, tmpPath }) => {
    const fileName = 'var-syntax-test.ipynb';
    
    await page.notebook.createNew(fileName);
    
    // Define a variable in kernel
    await page.notebook.setCell(0, 'code', 'my_variable = 123');
    await page.notebook.runCell(0);
    await expect(page.locator('.jp-InputArea-prompt:has-text("[1]")')).toBeVisible({ timeout: 10000 });
    
    // Insert prompt with $variable syntax
    await page.notebook.selectCells(0);
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
    await page.notebook.setCell(0, 'code', 'def my_function(x):\n    return x * 2');
    await page.notebook.runCell(0);
    await expect(page.locator('.jp-InputArea-prompt:has-text("[1]")')).toBeVisible({ timeout: 10000 });
    
    // Insert prompt with &function syntax
    await page.notebook.selectCells(0);
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
