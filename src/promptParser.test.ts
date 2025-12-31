/**
 * Tests for promptParser.ts
 */

import {
  parsePrompt,
  substituteVariables,
  removeFunctionReferences,
  processPrompt
} from './promptParser';

describe('parsePrompt', () => {
  describe('variable parsing', () => {
    it('should extract single variable', () => {
      const result = parsePrompt('What about $sales_data?');
      expect(result.variables).toEqual(['sales_data']);
    });

    it('should extract multiple variables', () => {
      const result = parsePrompt('Use $x and $y together');
      expect(result.variables).toContain('x');
      expect(result.variables).toContain('y');
      expect(result.variables).toHaveLength(2);
    });

    it('should deduplicate variables', () => {
      const result = parsePrompt('$x plus $x equals 2x');
      expect(result.variables).toEqual(['x']);
    });

    it('should not match invalid variable syntax (starts with number)', () => {
      const result = parsePrompt('this $123 is not valid');
      expect(result.variables).toEqual([]);
    });

    it('should handle underscores in variable names', () => {
      const result = parsePrompt('Check $__hidden and $my_var');
      expect(result.variables).toContain('__hidden');
      expect(result.variables).toContain('my_var');
    });

    it('should handle variable at end of string', () => {
      const result = parsePrompt('The value is $x');
      expect(result.variables).toEqual(['x']);
    });

    it('should handle variable followed by punctuation', () => {
      const result = parsePrompt('Check $x, and $y.');
      expect(result.variables).toContain('x');
      expect(result.variables).toContain('y');
    });
  });

  describe('function parsing', () => {
    it('should extract single function', () => {
      const result = parsePrompt('Use &calculate_metrics');
      expect(result.functions).toEqual(['calculate_metrics']);
    });

    it('should extract multiple functions', () => {
      const result = parsePrompt('&func1 and &func2');
      expect(result.functions).toContain('func1');
      expect(result.functions).toContain('func2');
    });

    it('should deduplicate functions', () => {
      const result = parsePrompt('&add then &add again');
      expect(result.functions).toEqual(['add']);
    });

    it('should not match ampersand inside words', () => {
      const result = parsePrompt('cost&benefit analysis');
      expect(result.functions).toEqual([]);
    });

    it('should not match invalid function syntax', () => {
      const result = parsePrompt('this &123 is not valid');
      expect(result.functions).toEqual([]);
    });

    it('should handle function at start of string', () => {
      const result = parsePrompt('&helper is useful');
      expect(result.functions).toEqual(['helper']);
    });

    it('should handle function followed by punctuation', () => {
      const result = parsePrompt('Use &func, please.');
      expect(result.functions).toEqual(['func']);
    });

    it('should handle underscores in function names', () => {
      const result = parsePrompt('Use &__private and &my_func');
      expect(result.functions).toContain('__private');
      expect(result.functions).toContain('my_func');
    });
  });

  describe('mixed parsing', () => {
    it('should extract both variables and functions', () => {
      const result = parsePrompt('$data with &process');
      expect(result.variables).toEqual(['data']);
      expect(result.functions).toEqual(['process']);
    });

    it('should handle complex prompt with multiple of each', () => {
      const result = parsePrompt(`
        Given $input_data and $config,
        use &analyze and &summarize to process.
      `);
      expect(result.variables).toContain('input_data');
      expect(result.variables).toContain('config');
      expect(result.functions).toContain('analyze');
      expect(result.functions).toContain('summarize');
    });

    it('should handle variable and function in same prompt', () => {
      const result = parsePrompt('Use $data with &func');
      expect(result.variables).toEqual(['data']);
      expect(result.functions).toEqual(['func']);
    });
  });

  describe('markdown formatted prompts', () => {
    it('should handle variables in lists', () => {
      const result = parsePrompt(`
        - Use $x
        - Check $y
      `);
      expect(result.variables).toContain('x');
      expect(result.variables).toContain('y');
    });

    it('should handle functions with descriptions', () => {
      const result = parsePrompt(`
        - &view: View files
        - &create: Create files
      `);
      expect(result.functions).toContain('view');
      expect(result.functions).toContain('create');
    });
  });
});

describe('substituteVariables', () => {
  it('should substitute single variable', () => {
    const result = substituteVariables('Value is $x', { x: '42' });
    expect(result).toBe('Value is 42');
  });

  it('should substitute multiple variables', () => {
    const result = substituteVariables('$a + $b = $c', { a: '1', b: '2', c: '3' });
    expect(result).toBe('1 + 2 = 3');
  });

  it('should handle word boundaries correctly', () => {
    const result = substituteVariables('$id and $id2', { id: 'A', id2: 'B' });
    expect(result).toBe('A and B');
  });

  it('should not substitute partial matches', () => {
    const result = substituteVariables('$id and $identifier', { id: 'X' });
    expect(result).toBe('X and $identifier');
  });

  it('should handle special regex chars in values', () => {
    const result = substituteVariables('Price is $price', { price: '$5 & more' });
    expect(result).toBe('Price is $5 & more');
  });

  it('should handle regex pattern in value', () => {
    const result = substituteVariables('Pattern: $pattern', { pattern: '\\d+.*$' });
    expect(result).toBe('Pattern: \\d+.*$');
  });

  it('should preserve multiline values', () => {
    const result = substituteVariables('Data: $data', { data: 'line1\nline2' });
    expect(result).toBe('Data: line1\nline2');
  });

  it('should preserve unicode values', () => {
    const result = substituteVariables('Greek: $alpha', { alpha: 'α β γ' });
    expect(result).toBe('Greek: α β γ');
  });

  it('should leave unknown variables untouched', () => {
    const result = substituteVariables('$known and $unknown', { known: 'X' });
    expect(result).toBe('X and $unknown');
  });

  it('should handle empty values', () => {
    const result = substituteVariables('Value: $x end', { x: '' });
    expect(result).toBe('Value:  end');
  });
});

describe('removeFunctionReferences', () => {
  it('should remove single function reference', () => {
    const result = removeFunctionReferences('Use &func to help');
    expect(result).toBe('Use to help');
  });

  it('should remove multiple function references', () => {
    const result = removeFunctionReferences('Use &f1 and &f2 now');
    expect(result).toBe('Use and now');
  });

  it('should handle function at start', () => {
    const result = removeFunctionReferences('&func first');
    expect(result).toBe('first');
  });

  it('should handle function at end', () => {
    const result = removeFunctionReferences('Call &func');
    expect(result).toBe('Call');
  });

  it('should not remove ampersand in words', () => {
    const result = removeFunctionReferences('cost&benefit');
    expect(result).toBe('cost&benefit');
  });

  it('should normalize whitespace', () => {
    const result = removeFunctionReferences('Use  &f1   and   &f2  now');
    expect(result).toBe('Use and now');
  });

  it('should handle function next to punctuation', () => {
    const result = removeFunctionReferences('Use &func, please');
    expect(result).toBe('Use , please');
  });
});

describe('processPrompt', () => {
  it('should substitute variables and remove functions', () => {
    const result = processPrompt('Analyze $data using &analyze', { data: '[1,2,3]' });
    expect(result).toBe('Analyze [1,2,3] using');
  });

  it('should handle complex prompt', () => {
    const result = processPrompt(
      'Given $x and $y, use &add to compute result',
      { x: '5', y: '10' }
    );
    expect(result).toBe('Given 5 and 10, use to compute result');
  });

  it('should trim result', () => {
    const result = processPrompt('  &func start  ', {});
    expect(result).toBe('start');
  });

  it('should handle empty input', () => {
    const result = processPrompt('', {});
    expect(result).toBe('');
  });

  it('should handle prompt with only variables', () => {
    const result = processPrompt('Value: $x', { x: '42' });
    expect(result).toBe('Value: 42');
  });

  it('should handle prompt with only functions', () => {
    const result = processPrompt('Use &helper and &analyzer', {});
    expect(result).toBe('Use and');
  });
});

describe('edge cases', () => {
  it('should handle dollar sign in replacement value (no $& expansion)', () => {
    const result = substituteVariables('Price: $price', { price: '$100' });
    expect(result).toBe('Price: $100');
  });

  it('should handle $$ in value', () => {
    const result = substituteVariables('Money: $amount', { amount: '$$500$$' });
    expect(result).toBe('Money: $$500$$');
  });

  it('should handle very long variable names', () => {
    const longName = 'a'.repeat(100);
    const result = parsePrompt(`$${longName}`);
    expect(result.variables).toEqual([longName]);
  });

  it('should handle adjacent variable references', () => {
    const result = parsePrompt('$a$b$c');
    expect(result.variables).toContain('a');
    expect(result.variables).toContain('b');
    expect(result.variables).toContain('c');
  });
});
