import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const OUT_DIR = process.env.OUT_DIR || "/root/myphotos/ui_shots/responsive2";

// Pick concrete assets so we can verify portrait vs landscape media in viewer.
const ASSET_VIDEO = process.env.ASSET_VIDEO || "623ea57e-72f6-4f90-8965-89d1505f0354";
const ASSET_PHOTO_PORTRAIT = process.env.ASSET_PHOTO_PORTRAIT || "41a0fdf7-329a-4c1e-a827-c2a5ed7774ba";
const ASSET_PHOTO_LANDSCAPE = process.env.ASSET_PHOTO_LANDSCAPE || "63c25b33-476f-4d03-afcf-2911b29914ee";

fs.mkdirSync(OUT_DIR, { recursive: true });

let viewports = [
  { name: "desktop-1440x900", width: 1440, height: 900 },
  { name: "laptop-1280x720", width: 1280, height: 720 },
  { name: "tablet-768x1024-portrait", width: 768, height: 1024 },
  { name: "tablet-1024x768-landscape", width: 1024, height: 768 },
  { name: "phone-390x844-portrait", width: 390, height: 844 },
  { name: "phone-844x390-landscape", width: 844, height: 390 },
  { name: "phone-small-360x640-portrait", width: 360, height: 640 },
  { name: "phone-small-640x360-landscape", width: 640, height: 360 }
];

if (process.env.ONLY_VIEWPORT) {
  viewports = viewports.filter((vp) => vp.name === process.env.ONLY_VIEWPORT);
}


function out(name) {
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  return path.join(OUT_DIR, `${ts}-${name}.png`);
}

async function openViewerForAsset(page, assetId) {
  await page.goto(`${BASE}/app/timeline?viewer=1&asset=${assetId}`, { waitUntil: "domcontentloaded" });
  const overlay = page.locator(".viewer-overlay");
  await overlay.waitFor({ state: "visible" });
  await page.waitForTimeout(800);
}

async function openQualityMenu(page) {
  // The video element can intercept pointer events in some states.
  // Use forced click and (if needed) DOM click to open the menu.
  const btn = page.locator(".vjs-quality-select-control").first();
  if ((await btn.count()) === 0) return false;

  try {
    await btn.click({ timeout: 5_000, force: true });
  } catch {
    try {
      await page.evaluate(() => {
        const el = document.querySelector(".vjs-quality-select-control");
        if (el && el instanceof HTMLElement) el.click();
      });
    } catch {
      return true; // control exists but couldn't click
    }
  }

  await page.waitForTimeout(400);
  return true;
}

async function collectViewerLayout(page) {
  return await page.evaluate(() => {
    const pick = (sel) => document.querySelector(sel);
    const rect = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height, top: r.top, left: r.left, right: r.right, bottom: r.bottom };
    };
    const style = (el) => {
      if (!el) return null;
      const cs = window.getComputedStyle(el);
      return {
        display: cs.display,
        position: cs.position,
        width: cs.width,
        height: cs.height,
        maxWidth: cs.maxWidth,
        maxHeight: cs.maxHeight,
        objectFit: cs.objectFit,
        objectPosition: cs.objectPosition,
        placeSelf: (cs.placeSelf || undefined),
        alignSelf: cs.alignSelf,
        justifySelf: cs.justifySelf,
        transform: cs.transform,
        overflow: cs.overflow,
        overflowX: cs.overflowX,
        overflowY: cs.overflowY,
      };
    };

    const media = pick('.viewer-media');
    const img = pick('.viewer-media img.viewer-media-item');
    const nav = pick('.viewer-hover-nav');
    const prev = pick('.viewer-arrow.prev');
    const next = pick('.viewer-arrow.next');

    const imgInfo = img && img instanceof HTMLImageElement
      ? {
          className: img.className,
          styleAttr: img.getAttribute('style'),
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight,
          currentSrc: img.currentSrc,
          complete: img.complete,
        }
      : null;

    return {
      viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio },
      media: { rect: rect(media), style: style(media) },
      img: { rect: rect(img), style: style(img), ...imgInfo },
      nav: { rect: rect(nav), style: style(nav) },
      prev: { rect: rect(prev), style: style(prev) },
      next: { rect: rect(next), style: style(next) },
    };
  });
}

async function snapViewer(page, vp, label, assetId) {
  await openViewerForAsset(page, assetId);
  const layout = await collectViewerLayout(page);
  console.log(`VIEWER_LAYOUT ${JSON.stringify({ kind: "viewer_layout", viewport: vp.name, label, layout })}`);
  await page.screenshot({ path: out(`${vp.name}-viewer-${label}`), fullPage: false });

  // Let controls hide, then snap for overlap check.
  await page.waitForTimeout(11_500);
  await page.screenshot({ path: out(`${vp.name}-viewer-${label}-after-12s`), fullPage: false });

  // Show controls again.
  await page.mouse.move(50, 50);
  await page.waitForTimeout(500);

  // Quality menu if present.
  const hasQuality = await openQualityMenu(page);
  if (hasQuality) {
    await page.screenshot({ path: out(`${vp.name}-viewer-${label}-quality-open`), fullPage: false });
  }
}

async function snapshotViewport(page, vp) {
  await page.setViewportSize({ width: vp.width, height: vp.height });

  // Timeline (for nav layout)
  await page.goto(`${BASE}/app/timeline`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: out(`${vp.name}-timeline`), fullPage: false });

  // Viewer: portrait photo, landscape photo, then video
  await snapViewer(page, vp, "photo-portrait", ASSET_PHOTO_PORTRAIT);
  await snapViewer(page, vp, "photo-landscape", ASSET_PHOTO_LANDSCAPE);
  await snapViewer(page, vp, "video", ASSET_VIDEO);
}

async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    args: ["--no-sandbox", "--disable-gpu"],
  });

  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  page.setDefaultTimeout(60_000);

  for (const vp of viewports) {
    await snapshotViewport(page, vp);
  }

  await browser.close();
  console.log(JSON.stringify({ base: BASE, outDir: OUT_DIR, viewports, assets: { ASSET_PHOTO_PORTRAIT, ASSET_PHOTO_LANDSCAPE, ASSET_VIDEO } }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
