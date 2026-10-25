import { defineConfig } from 'vitest/config';

// Only the framework-free logic under src/app/lib is tested here: time
// formatting, delay text, staleness, station helpers. No Angular, no DOM.
export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.spec.ts'],
  },
});
