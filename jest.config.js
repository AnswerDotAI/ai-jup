/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src'],
  testMatch: ['**/*.test.ts'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json'],
  collectCoverageFrom: ['src/**/*.ts', '!src/**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: {
        module: 'commonjs',
        esModuleInterop: true,
        allowSyntheticDefaultImports: true,
        strict: true,
        skipLibCheck: true,
        noEmit: true,
      }
    }]
  },
  moduleNameMapper: {
    // Mock JupyterLab dependencies that aren't available in Node
    '@jupyterlab/(.*)': '<rootDir>/src/__mocks__/jupyterlab.ts',
    '@lumino/(.*)': '<rootDir>/src/__mocks__/lumino.ts',
  }
};
