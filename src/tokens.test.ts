/**
 * Tests for DI tokens and interfaces.
 */

import {
  IKernelConnectorFactory,
  IPromptCellManager,
  IPromptModelFactory,
  IExtensionSettings
} from './tokens';

describe('DI Tokens', () => {
  describe('IKernelConnectorFactory token', () => {
    it('should have correct id', () => {
      expect(IKernelConnectorFactory.name).toBe('ai-jup:IKernelConnectorFactory');
    });
    
    it('should have description', () => {
      expect(IKernelConnectorFactory.description).toBe('Factory for creating kernel connectors');
    });
  });
  
  describe('IPromptCellManager token', () => {
    it('should have correct id', () => {
      expect(IPromptCellManager.name).toBe('ai-jup:IPromptCellManager');
    });
    
    it('should have description', () => {
      expect(IPromptCellManager.description).toBe('Manages prompt cells within notebooks');
    });
  });
  
  describe('IPromptModelFactory token', () => {
    it('should have correct id', () => {
      expect(IPromptModelFactory.name).toBe('ai-jup:IPromptModelFactory');
    });
    
    it('should have description', () => {
      expect(IPromptModelFactory.description).toBe('Factory for creating prompt models');
    });
  });
  
  describe('IExtensionSettings token', () => {
    it('should have correct id', () => {
      expect(IExtensionSettings.name).toBe('ai-jup:IExtensionSettings');
    });
    
    it('should have description', () => {
      expect(IExtensionSettings.description).toBe('Extension configuration settings');
    });
  });
});

describe('Token uniqueness', () => {
  it('all tokens should have unique names', () => {
    const names = [
      IKernelConnectorFactory.name,
      IPromptCellManager.name,
      IPromptModelFactory.name,
      IExtensionSettings.name
    ];
    
    const uniqueNames = new Set(names);
    expect(uniqueNames.size).toBe(names.length);
  });
});
