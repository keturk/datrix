/** Jest configuration for examples.IngestionService */

export default {
  preset: 'ts-jest',
  testEnvironment: 'node',
  setupFiles: ['reflect-metadata'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: ['**/*.spec.ts', '**/*.test.ts'],
  testPathIgnorePatterns: [
    '/node_modules/',
    '/dist/',
    'deploy_tests\\.spec\\.ts$',
    '/test/controllers/',
    '/test/routes/',
    '/test/integration/',
    '/test/spec/', // Spec tests run as deploy tests, not unit tests
  ],
  transform: {
    '^.+\\.ts$': ['ts-jest', { isolatedModules: true }],
  },
  workerIdleMemoryLimit: '512MB',
};
