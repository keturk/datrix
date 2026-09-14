/** Jest configuration for ecommerce.ProductService */

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
    // test/deployment/ boots the full AppModule. With RDBMS blocks present that
    // means MikroORM opens a real connection during app.init(), so the suite
    // cannot pass without a database -- it runs under jest-integration.config.ts,
    // which supplies TEST_DATABASE_URL. Services with no RDBMS block boot with no
    // connection at all, and keep the suite here as a genuine unit test.
    '/test/deployment/',
    // test/graphql/ boots the full AppModule the same way (Test.createTestingModule
    // + app.init()), so it carries the identical database requirement and moves to
    // jest-integration.config.ts for the same reason. Left here it fails with a
    // bare AggregateError (the driver's ECONNREFUSED) on every DB-less unit run.
    '/test/graphql/',
  ],
  transform: {
    '^.+\\.ts$': ['ts-jest', { isolatedModules: true }],
  },
  workerIdleMemoryLimit: '512MB',
};
