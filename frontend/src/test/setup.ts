import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom does not implement media playback APIs. The app uses play()/pause() for
// hover previews and live-photo playback, so provide harmless stubs.
Object.defineProperty(HTMLMediaElement.prototype, "play", {
  configurable: true,
  // eslint-disable-next-line @typescript-eslint/no-misused-promises
  value: vi.fn().mockResolvedValue(undefined)
});

Object.defineProperty(HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: vi.fn()
});
