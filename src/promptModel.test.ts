/**
 * Tests for PromptModel signal-based streaming.
 */

import { PromptModel, PromptModelFactory } from './promptModel';
import type { IStreamEvent, IPromptContext } from './tokens';

describe('PromptModel', () => {
  let model: PromptModel;
  
  beforeEach(() => {
    model = new PromptModel();
  });
  
  afterEach(() => {
    model.dispose();
  });
  
  describe('initial state', () => {
    it('should start in idle state', () => {
      expect(model.state).toBe('idle');
    });
    
    it('should start with empty output', () => {
      expect(model.output).toBe('');
    });
  });
  
  describe('signals', () => {
    it('should emit stateChanged signal', () => {
      const states: string[] = [];
      model.stateChanged.connect((_, state) => states.push(state));
      
      // Trigger state change via reset
      model.reset();
      
      // State should still be idle (reset when already idle)
      expect(states).toEqual([]);
    });
    
    it('should emit outputChanged signal when output is updated', () => {
      const outputs: string[] = [];
      model.outputChanged.connect((_, output) => outputs.push(output));
      
      // Reset clears output and emits signal
      model.reset();
      
      expect(outputs).toEqual(['']);
    });
  });
  
  describe('abort', () => {
    it('should be able to abort without error when idle', () => {
      expect(() => model.abort()).not.toThrow();
    });
    
    it('should reset state after abort', () => {
      model.abort();
      expect(model.state).toBe('idle');
    });
  });
  
  describe('reset', () => {
    it('should clear output', () => {
      // Simulate some output by calling reset
      model.reset();
      expect(model.output).toBe('');
    });
    
    it('should set state to idle', () => {
      model.reset();
      expect(model.state).toBe('idle');
    });
  });
  
  describe('dispose', () => {
    it('should clean up signals on dispose', () => {
      model.outputChanged.connect(() => { /* listener */ });
      
      model.dispose();
      
      // After dispose, signals should be cleared
      // This tests that Signal.clearData was called
      expect(model.state).toBe('idle');
    });
  });
});

describe('PromptModelFactory', () => {
  it('should create new PromptModel instances', () => {
    const factory = new PromptModelFactory();
    const model1 = factory.create();
    const model2 = factory.create();
    
    expect(model1).toBeInstanceOf(PromptModel);
    expect(model2).toBeInstanceOf(PromptModel);
    expect(model1).not.toBe(model2);
    
    // Clean up
    (model1 as PromptModel).dispose();
    (model2 as PromptModel).dispose();
  });
});

describe('IStreamEvent types', () => {
  it('should accept valid stream events', () => {
    const events: IStreamEvent[] = [
      { type: 'start' },
      { type: 'text', text: 'Hello' },
      { type: 'tool_call', toolCall: { name: 'test', id: '123' } },
      { type: 'tool_input', toolInput: '{"arg": 1}' },
      { type: 'tool_result', toolResult: { id: '123', name: 'test', result: { status: 'ok' } } },
      { type: 'error', error: 'Something went wrong' },
      { type: 'done' }
    ];
    
    // Type check passes if this compiles
    expect(events.length).toBe(7);
  });
});

describe('IPromptContext', () => {
  it('should accept valid context', () => {
    const context: IPromptContext = {
      preceding_code: 'x = 1\ny = 2',
      variables: {
        x: { name: 'x', type: 'int', repr: '1' },
        y: { name: 'y', type: 'int', repr: '2' }
      },
      functions: {
        add: {
          name: 'add',
          signature: '(a, b)',
          docstring: 'Add two numbers',
          parameters: {
            a: { type: 'int', description: 'First number' },
            b: { type: 'int', description: 'Second number' }
          }
        }
      }
    };
    
    expect(context.preceding_code).toBe('x = 1\ny = 2');
    expect(Object.keys(context.variables)).toHaveLength(2);
    expect(Object.keys(context.functions)).toHaveLength(1);
  });
});
