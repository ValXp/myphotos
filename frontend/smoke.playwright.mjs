import { chromium, request } from 'playwright';

const FRONTEND = 'http://127.0.0.1:5173/';
const BACKEND_READY = 'http://127.0.0.1:8000/ready';

const browser = await chromium.launch();
const page = await browser.newPage();

await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });
const bodyText = await page.locator('body').innerText();
if (!/sign in|passkey|login/i.test(bodyText)) {
  throw new Error('Expected sign-in UI text to appear on landing page, but did not find it.');
}

const api = await request.newContext();
const res = await api.get(BACKEND_READY);
if (!res.ok()) throw new Error(`/ready not ok: ${res.status()}`);

console.log('OK: frontend renders sign-in UI, backend /ready is OK.');
await api.dispose();
await browser.close();
