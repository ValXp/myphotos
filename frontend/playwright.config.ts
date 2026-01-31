import { defineConfig } from '@playwright/test';

const BACKEND_PORT = 8000;
const E2E_DB = 'myphotos_e2e';

export default defineConfig({
  testDir: './e2e',
  // Keep e2e deterministic by running serially.
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    // Serve the built frontend bundle from the backend so WebAuthn and API calls
    // are same-origin (avoids CORS/proxy complexity in tests).
    // WebAuthn does NOT allow an RP ID of an IP address, so use localhost.
    baseURL: `http://localhost:${BACKEND_PORT}`,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: [
      'bash -lc',
      '"'
        + `su - postgres -c \\\"dropdb --if-exists ${E2E_DB}; createdb -O myphotos ${E2E_DB}\\\" && `
        + 'cd .. && '
        + 'cd frontend && npm run build && cd .. && '
        + 'source .venv/bin/activate && '
        + `export DB_URL=postgresql+psycopg://myphotos:myphotos@localhost:5432/${E2E_DB} && `
        + 'export REDIS_URL=redis://localhost:6379/0 && '
        + `export APP_HOST=127.0.0.1 APP_PORT=${BACKEND_PORT} APP_ENV=development && `
        + 'export FRONTEND_DIST_DIR=../frontend/dist && '
        + 'export WEBAUTHN_RP_ID=localhost && '
        + `export WEBAUTHN_ORIGINS=\\\"http://localhost:${BACKEND_PORT}\\\" && `
        + './migrate up && '
        + 'cd backend && '
        + `uvicorn app.api.app:app --host 127.0.0.1 --port ${BACKEND_PORT}`
        + '"',
    ].join(' '),
    url: `http://localhost:${BACKEND_PORT}/ready`,
    reuseExistingServer: false,
    timeout: 240_000,
  },
});
