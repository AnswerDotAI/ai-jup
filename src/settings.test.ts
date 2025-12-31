/**
 * Tests for SettingsManager.
 */

import { SettingsManager } from './settings';

describe('SettingsManager', () => {
  let settings: SettingsManager;
  
  beforeEach(() => {
    settings = new SettingsManager();
  });
  
  afterEach(() => {
    settings.dispose();
  });
  
  describe('default values', () => {
    it('should have default model', () => {
      expect(settings.defaultModel).toBe('claude-sonnet-4-20250514');
    });
    
    it('should have default maxToolSteps', () => {
      expect(settings.maxToolSteps).toBe(5);
    });
    
    it('should have default showConvertButton', () => {
      expect(settings.showConvertButton).toBe(true);
    });
  });
  
  describe('toJSON', () => {
    it('should return all settings as object', () => {
      const json = settings.toJSON();
      
      expect(json).toEqual({
        defaultModel: 'claude-sonnet-4-20250514',
        maxToolSteps: 5,
        showConvertButton: true
      });
    });
  });
  
  describe('settingsChanged signal', () => {
    it('should exist', () => {
      expect(settings.settingsChanged).toBeDefined();
    });
  });
  
  describe('dispose', () => {
    it('should not throw when disposing', () => {
      expect(() => settings.dispose()).not.toThrow();
    });
    
    it('should allow multiple dispose calls', () => {
      settings.dispose();
      expect(() => settings.dispose()).not.toThrow();
    });
  });
});

describe('IExtensionSettings interface', () => {
  it('SettingsManager should implement IExtensionSettings', () => {
    const settings = new SettingsManager();
    
    // These should all exist and be the correct types
    expect(typeof settings.defaultModel).toBe('string');
    expect(typeof settings.maxToolSteps).toBe('number');
    expect(typeof settings.showConvertButton).toBe('boolean');
    
    settings.dispose();
  });
});
