import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: [
      'src/__tests__/**/*.test.ts',
      'public/js/__tests__/**/*.test.js',
    ],
    coverage: {
      provider: 'v8',
      include: [
        'src/**/*.ts',
        'public/js/**/*.js',
      ],
      exclude: [
        'src/server.ts',
        'src/types.ts',
        'dist/**',
      ],
      thresholds: {
        lines: 80,
        functions: 90,
        branches: 75,
      },
    },
    pool: 'forks',
    testTimeout: 10000,
  },
});
