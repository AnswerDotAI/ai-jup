/**
 * Mock JupyterLab modules for Jest tests.
 */

export const PageConfig = {
  getBaseUrl: () => 'http://localhost:8888/'
};

export class ISettingRegistry {
  static load = jest.fn();
}
