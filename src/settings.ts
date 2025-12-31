/**
 * Settings management for ai-jup extension.
 * 
 * Integrates with JupyterLab's ISettingRegistry for persistent configuration.
 */

import { ISettingRegistry } from '@jupyterlab/settingregistry';
import { Signal, ISignal } from '@lumino/signaling';
import { IExtensionSettings } from './tokens';

const PLUGIN_ID = 'ai-jup:plugin';

/**
 * Default settings values.
 */
const DEFAULT_SETTINGS: IExtensionSettings = {
  defaultModel: 'claude-sonnet-4-20250514',
  maxToolSteps: 5,
  showConvertButton: true
};

/**
 * Settings manager that wraps ISettingRegistry.
 */
export class SettingsManager implements IExtensionSettings {
  private _settings: ISettingRegistry.ISettings | null = null;
  private _defaultModel: string = DEFAULT_SETTINGS.defaultModel;
  private _maxToolSteps: number = DEFAULT_SETTINGS.maxToolSteps;
  private _showConvertButton: boolean = DEFAULT_SETTINGS.showConvertButton;
  private _settingsChanged = new Signal<this, void>(this);

  /**
   * Signal emitted when settings change.
   */
  get settingsChanged(): ISignal<this, void> {
    return this._settingsChanged;
  }

  get defaultModel(): string {
    return this._defaultModel;
  }

  get maxToolSteps(): number {
    return this._maxToolSteps;
  }

  get showConvertButton(): boolean {
    return this._showConvertButton;
  }

  /**
   * Initialize settings from the registry.
   */
  async initialize(registry: ISettingRegistry): Promise<void> {
    try {
      this._settings = await registry.load(PLUGIN_ID);
      this._updateFromSettings();
      this._settings.changed.connect(this._onSettingsChanged, this);
    } catch (error) {
      console.warn('[ai-jup] Failed to load settings, using defaults:', error);
    }
  }

  /**
   * Update a setting value.
   */
  async set<K extends keyof IExtensionSettings>(
    key: K,
    value: IExtensionSettings[K]
  ): Promise<void> {
    if (this._settings) {
      await this._settings.set(key, value);
    }
  }

  /**
   * Get all settings as a plain object.
   */
  toJSON(): IExtensionSettings {
    return {
      defaultModel: this._defaultModel,
      maxToolSteps: this._maxToolSteps,
      showConvertButton: this._showConvertButton
    };
  }

  private _onSettingsChanged(): void {
    this._updateFromSettings();
    this._settingsChanged.emit();
  }

  private _updateFromSettings(): void {
    if (!this._settings) return;

    const composite = this._settings.composite;
    
    this._defaultModel =
      (composite['defaultModel'] as string) ?? DEFAULT_SETTINGS.defaultModel;
    this._maxToolSteps =
      (composite['maxToolSteps'] as number) ?? DEFAULT_SETTINGS.maxToolSteps;
    this._showConvertButton =
      (composite['showConvertButton'] as boolean) ?? DEFAULT_SETTINGS.showConvertButton;
  }

  /**
   * Dispose of the settings manager.
   */
  dispose(): void {
    if (this._settings) {
      this._settings.changed.disconnect(this._onSettingsChanged, this);
    }
    Signal.clearData(this);
  }
}
