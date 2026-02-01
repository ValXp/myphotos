import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const shareUrl = process.env.SHARE_URL || `${baseURL}/share/iNZ7gndwf4L2FPTK9BVl8DLqBrknBQBnm5TWiMOSoLk`;
const outDir = process.env.OUT_DIR || '/root/myphotos/frontend/ui_screens';

await fs.mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });

const ts = new Date().toISOString().replace(/[:.]/g, '-');

console.log('Opening', shareUrl);
await page.goto(shareUrl, { waitUntil: 'domcontentloaded', timeout: 120_000 });
await page.waitForTimeout(1500);

async function snap(label) {
  const png = path.join(outDir, `${label}-${ts}.png`);
  const html = path.join(outDir, `${label}-${ts}.html`);
  await page.screenshot({ path: png, fullPage: true });
  await fs.writeFile(html, await page.content(), 'utf8');
  console.log('Wrote', png);
  console.log('Wrote', html);
}

await snap('share-page');

// Click the VIDEO card.
const videoCard = page.locator('article.media-card:has-text("VIDEO")').first();
if (await videoCard.count()) {
  await videoCard.locator('.media-thumb').click({ timeout: 30_000 });
} else {
  await page.locator('article.media-card').nth(2).locator('.media-thumb').click({ timeout: 30_000 });
}

await page.waitForTimeout(1500);
await snap('viewer');

// Wait for video.js controls and capture controlbar.
await page.waitForSelector('.vjs-control-bar', { timeout: 60_000 });
await page.waitForSelector('.vjs-quality-select-control', { timeout: 60_000 });

await page.hover('.video-js');
await page.waitForTimeout(1000);

const barShot = path.join(outDir, `controlbar-${ts}.png`);
await page.locator('.vjs-control-bar').first().screenshot({ path: barShot });
console.log('Wrote', barShot);

const qShot = path.join(outDir, `quality-select-${ts}.png`);
await page.locator('.vjs-quality-select-control').first().screenshot({ path: qShot });
console.log('Wrote', qShot);

// Layout assertion: quality dropdown must not overlap fullscreen.
const qBox = await page.locator('.vjs-quality-select').first().boundingBox();
const fsBox = await page.locator('.vjs-fullscreen-control').first().boundingBox();
if (qBox && fsBox) {
  const overlapX = qBox.x < fsBox.x + fsBox.width && qBox.x + qBox.width > fsBox.x;
  const overlapY = qBox.y < fsBox.y + fsBox.height && qBox.y + qBox.height > fsBox.y;
  if (overlapX && overlapY) {
    throw new Error(`Quality selector overlaps fullscreen: q=${JSON.stringify(qBox)} fs=${JSON.stringify(fsBox)}`);
  }
}

await browser.close();
