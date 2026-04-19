/** Jest configuration for ecommerce.OrderService */

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
    'unit_tests\\.spec\\.ts$',
    '/test/controllers/',
    '/test/routes/',
    '/test/integration/',
  ],
  transform: {
    '^.+\\.ts$': ['ts-jest', { isolatedModules: true }],
  },
  workerIdleMemoryLimit: '512MB',
};
