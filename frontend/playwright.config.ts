import { defineConfig } from '@playwright/test';

const BACKEND_PORT = 8000;

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 10_000 },
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
        + 'cd ../frontend && npm run build && '
        + 'cd ../backend && '
        + 'source ../.venv/bin/activate && '
        + `DB_URL=postgresql+psycopg://myphotos:myphotos@localhost:5432/myphotos `
        + `REDIS_URL=redis://localhost:6379/0 `
        + `APP_HOST=127.0.0.1 APP_PORT=${BACKEND_PORT} APP_ENV=development `
        + 'FRONTEND_DIST_DIR=../frontend/dist '
        + 'WEBAUTHN_RP_ID=localhost '
        + `WEBAUTHN_ORIGINS=\\\"http://localhost:${BACKEND_PORT}\\\" `
        + `uvicorn app.api.app:app --host 127.0.0.1 --port ${BACKEND_PORT}`
        + '"',
    ].join(' '),
    url: `http://localhost:${BACKEND_PORT}/ready`,
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
