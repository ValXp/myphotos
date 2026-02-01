import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { configDefaults } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist"
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    clearMocks: true,
    exclude: [...configDefaults.exclude, "e2e/**", "**/e2e/**"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/test/**",
        "src/**/*.test.{ts,tsx}",
        "src/**/*.spec.{ts,tsx}",
        // Entry point is wiring only and hard to unit-test meaningfully.
        "src/main.tsx",
        // View components are covered by higher-level integration/e2e checks; unit coverage
        // focuses on shared logic (auth, hooks, routing glue).
        "src/views/**"
      ]
    }
  }
});
