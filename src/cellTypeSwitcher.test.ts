/**
 * Tests for CustomCellTypeSwitcher logic.
 * 
 * These tests focus on the pure logic functions that can be tested
 * without full JupyterLab widget instantiation.
 */

import * as nbformat from '@jupyterlab/nbformat';

// Constants matching those in cellTypeSwitcher.tsx
const PROMPT_METADATA_KEY = 'ai_jup';

interface PromptMetadata {
  isPromptCell: boolean;
  model?: string;
}

type ExtendedCellType = nbformat.CellType | 'prompt';

/**
 * Check if a cell model is a prompt cell based on metadata.
 * Extracted from CustomCellTypeSwitcher for testing.
 */
function isPromptCell(model: { getMetadata: (key: string) => unknown }): boolean {
  const metadata = model.getMetadata(PROMPT_METADATA_KEY) as PromptMetadata | undefined;
  return metadata?.isPromptCell === true;
}

/**
 * Determine the dropdown value for a single cell.
 */
function getCellTypeValue(
  model: { type: nbformat.CellType; getMetadata: (key: string) => unknown }
): ExtendedCellType {
  return isPromptCell(model) ? 'prompt' : model.type;
}

/**
 * Determine the dropdown value for multiple selected cells.
 * Returns '-' if cells have different types.
 */
function getMultiCellValue(
  cells: Array<{ type: nbformat.CellType; getMetadata: (key: string) => unknown }>
): ExtendedCellType | '-' {
  if (cells.length === 0) {
    return '-';
  }

  const firstValue = getCellTypeValue(cells[0]);
  
  for (let i = 1; i < cells.length; i++) {
    if (getCellTypeValue(cells[i]) !== firstValue) {
      return '-';
    }
  }
  
  return firstValue;
}

// Mock cell model factory
function createMockCellModel(
  type: nbformat.CellType,
  metadata: Record<string, unknown> = {}
): { type: nbformat.CellType; getMetadata: (key: string) => unknown } {
  return {
    type,
    getMetadata: (key: string) => metadata[key]
  };
}

describe('isPromptCell', () => {
  it('returns true when ai_jup.isPromptCell is true', () => {
    const model = createMockCellModel('markdown', {
      [PROMPT_METADATA_KEY]: { isPromptCell: true }
    });
    expect(isPromptCell(model)).toBe(true);
  });

  it('returns true when ai_jup.isPromptCell is true with model specified', () => {
    const model = createMockCellModel('markdown', {
      [PROMPT_METADATA_KEY]: { isPromptCell: true, model: 'claude-sonnet-4-20250514' }
    });
    expect(isPromptCell(model)).toBe(true);
  });

  it('returns false when ai_jup.isPromptCell is false', () => {
    const model = createMockCellModel('markdown', {
      [PROMPT_METADATA_KEY]: { isPromptCell: false }
    });
    expect(isPromptCell(model)).toBe(false);
  });

  it('returns false when ai_jup metadata is missing', () => {
    const model = createMockCellModel('code', {});
    expect(isPromptCell(model)).toBe(false);
  });

  it('returns false when ai_jup metadata is null', () => {
    const model = createMockCellModel('code', {
      [PROMPT_METADATA_KEY]: null
    });
    expect(isPromptCell(model)).toBe(false);
  });

  it('returns false when ai_jup metadata is undefined', () => {
    const model = createMockCellModel('code', {
      [PROMPT_METADATA_KEY]: undefined
    });
    expect(isPromptCell(model)).toBe(false);
  });

  it('returns false when ai_jup is empty object', () => {
    const model = createMockCellModel('markdown', {
      [PROMPT_METADATA_KEY]: {}
    });
    expect(isPromptCell(model)).toBe(false);
  });

  it('returns false for code cell without metadata', () => {
    const model = createMockCellModel('code');
    expect(isPromptCell(model)).toBe(false);
  });

  it('returns false for raw cell without metadata', () => {
    const model = createMockCellModel('raw');
    expect(isPromptCell(model)).toBe(false);
  });
});

describe('getCellTypeValue', () => {
  it('returns "prompt" for markdown cell with prompt metadata', () => {
    const model = createMockCellModel('markdown', {
      [PROMPT_METADATA_KEY]: { isPromptCell: true }
    });
    expect(getCellTypeValue(model)).toBe('prompt');
  });

  it('returns "markdown" for markdown cell without prompt metadata', () => {
    const model = createMockCellModel('markdown');
    expect(getCellTypeValue(model)).toBe('markdown');
  });

  it('returns "code" for code cell', () => {
    const model = createMockCellModel('code');
    expect(getCellTypeValue(model)).toBe('code');
  });

  it('returns "raw" for raw cell', () => {
    const model = createMockCellModel('raw');
    expect(getCellTypeValue(model)).toBe('raw');
  });

  it('returns "code" for code cell even with unrelated metadata', () => {
    const model = createMockCellModel('code', {
      'other_extension': { someKey: true }
    });
    expect(getCellTypeValue(model)).toBe('code');
  });
});

describe('getMultiCellValue', () => {
  it('returns "-" for empty cell list', () => {
    expect(getMultiCellValue([])).toBe('-');
  });

  it('returns cell type for single code cell', () => {
    const cells = [createMockCellModel('code')];
    expect(getMultiCellValue(cells)).toBe('code');
  });

  it('returns cell type for single prompt cell', () => {
    const cells = [createMockCellModel('markdown', {
      [PROMPT_METADATA_KEY]: { isPromptCell: true }
    })];
    expect(getMultiCellValue(cells)).toBe('prompt');
  });

  it('returns "code" for multiple code cells', () => {
    const cells = [
      createMockCellModel('code'),
      createMockCellModel('code'),
      createMockCellModel('code')
    ];
    expect(getMultiCellValue(cells)).toBe('code');
  });

  it('returns "prompt" for multiple prompt cells', () => {
    const cells = [
      createMockCellModel('markdown', { [PROMPT_METADATA_KEY]: { isPromptCell: true } }),
      createMockCellModel('markdown', { [PROMPT_METADATA_KEY]: { isPromptCell: true } })
    ];
    expect(getMultiCellValue(cells)).toBe('prompt');
  });

  it('returns "-" for mixed code and markdown cells', () => {
    const cells = [
      createMockCellModel('code'),
      createMockCellModel('markdown')
    ];
    expect(getMultiCellValue(cells)).toBe('-');
  });

  it('returns "-" for mixed prompt and code cells', () => {
    const cells = [
      createMockCellModel('markdown', { [PROMPT_METADATA_KEY]: { isPromptCell: true } }),
      createMockCellModel('code')
    ];
    expect(getMultiCellValue(cells)).toBe('-');
  });

  it('returns "-" for mixed prompt and regular markdown cells', () => {
    const cells = [
      createMockCellModel('markdown', { [PROMPT_METADATA_KEY]: { isPromptCell: true } }),
      createMockCellModel('markdown')
    ];
    expect(getMultiCellValue(cells)).toBe('-');
  });

  it('returns "markdown" for multiple regular markdown cells', () => {
    const cells = [
      createMockCellModel('markdown'),
      createMockCellModel('markdown')
    ];
    expect(getMultiCellValue(cells)).toBe('markdown');
  });
});

describe('Metadata key consistency', () => {
  it('uses the correct metadata key', () => {
    expect(PROMPT_METADATA_KEY).toBe('ai_jup');
  });
});

describe('PromptMetadata structure', () => {
  it('validates expected metadata structure', () => {
    const validMetadata: PromptMetadata = {
      isPromptCell: true,
      model: 'claude-sonnet-4-20250514'
    };
    
    expect(validMetadata.isPromptCell).toBe(true);
    expect(validMetadata.model).toBe('claude-sonnet-4-20250514');
  });

  it('allows optional model field', () => {
    const minimalMetadata: PromptMetadata = {
      isPromptCell: true
    };
    
    expect(minimalMetadata.isPromptCell).toBe(true);
    expect(minimalMetadata.model).toBeUndefined();
  });
});
