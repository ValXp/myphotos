import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useLivePhotoHover } from "./useLivePhotoHover";

describe("useLivePhotoHover", () => {
  it("plays and pauses videos when hovering", async () => {
    const video = document.createElement("video") as HTMLVideoElement;
    const play = vi.fn().mockResolvedValue(undefined);
    const pause = vi.fn();
    Object.defineProperty(video, "play", { value: play, configurable: true });
    Object.defineProperty(video, "pause", { value: pause, configurable: true });

    const { result } = renderHook(() => useLivePhotoHover());

    act(() => {
      result.current.registerVideoRef("asset-1")(video);
    });

    await act(async () => {
      result.current.handleMouseEnter("asset-1");
    });
    expect(play).toHaveBeenCalled();

    act(() => {
      result.current.handleMouseLeave("asset-1");
    });
    expect(pause).toHaveBeenCalled();

    act(() => {
      result.current.registerVideoRef("asset-1")(null);
    });

    play.mockClear();
    act(() => {
      result.current.handleMouseEnter("asset-1");
    });
    expect(play).not.toHaveBeenCalled();
  });

  it("skips videos marked as failed", () => {
    const video = document.createElement("video") as HTMLVideoElement;
    const play = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(video, "play", { value: play, configurable: true });
    video.dataset.failed = "true";

    const { result } = renderHook(() => useLivePhotoHover());

    act(() => {
      result.current.registerVideoRef("asset-1")(video);
      result.current.handleMouseEnter("asset-1");
    });

    expect(play).not.toHaveBeenCalled();
  });

  it("ignores playback/seek failures and missing refs", async () => {
    const video = document.createElement("video") as HTMLVideoElement;
    // Make seeking throw to hit the try/catch.
    Object.defineProperty(video, "currentTime", {
      configurable: true,
      set: () => {
        throw new Error("seek failed");
      }
    });

    const play = vi.fn().mockRejectedValue(new Error("autoplay"));
    Object.defineProperty(video, "play", { value: play, configurable: true });
    const pause = vi.fn();
    Object.defineProperty(video, "pause", { value: pause, configurable: true });

    const { result } = renderHook(() => useLivePhotoHover());

    // Missing refs are a no-op.
    act(() => {
      result.current.handleMouseLeave("missing");
    });

    act(() => {
      result.current.registerVideoRef("asset-1")(video);
    });

    await act(async () => {
      result.current.handleMouseEnter("asset-1");
      // Allow the rejection handler to run.
      await Promise.resolve();
    });

    act(() => {
      result.current.handleMouseLeave("asset-1");
    });

    expect(play).toHaveBeenCalled();
    expect(pause).toHaveBeenCalled();
  });
});
