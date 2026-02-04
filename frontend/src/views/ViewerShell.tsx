import { FocusEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import videojs from "video.js";
import "video.js/dist/video-js.css";

const CONTROLS_HIDE_DELAY_MS = 5_000;

let qualityLevelsPromise: Promise<void> | null = null;

async function ensureQualityLevels(): Promise<void> {
  if (typeof (videojs as any).getPlugin === "function") {
    const existing = (videojs as any).getPlugin("qualityLevels");
    if (existing) {
      return;
    }
  }
  if (!qualityLevelsPromise) {
    qualityLevelsPromise = import("videojs-contrib-quality-levels")
      .then(() => undefined)
      .catch(() => undefined);
  }
  await qualityLevelsPromise;
}

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC"
});

export type AssetType = "photo" | "video" | "live_photo";

export type ViewerAsset = {
  id: string;
  type: AssetType;
  captured_at: string | null;
  created_at: string | null;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  live_photo_video_id: string | null;
  ready?: {
    thumb?: boolean;
    stream?: boolean;
    live?: boolean;
  };
};

export type ViewerStatus = "idle" | "loading" | "ready" | "error";

type ViewerShellProps = {
  contextLabel: string;
  emptyMessage: string;
  emptySubhead: string;
  loadingMessage?: string;
  items: ViewerAsset[];
  status: ViewerStatus;
  error: string | null;
  nextCursor?: string | null;
  previewUrl: (assetId: string) => string;
  photoUrl?: (assetId: string) => string;
  fullPhotoUrl?: (assetId: string) => string;
  streamUrl: (assetId: string) => string;
  liveUrl?: (assetId: string) => string;
  backLink?: {
    to: string;
    label: string;
  };
  onClose?: () => void;
  showFooterNav?: boolean;
};

function assetTimestamp(asset: ViewerAsset): Date | null {
  const value = asset.captured_at ?? asset.created_at;
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function formatDateLabel(asset: ViewerAsset): string {
  const timestamp = assetTimestamp(asset);
  if (!timestamp) {
    return "Unknown date";
  }
  return dateFormatter.format(timestamp);
}

function formatDuration(durationMs: number | null, type: AssetType): string | null {
  if (type !== "video") {
    return null;
  }
  if (!durationMs || durationMs <= 0) {
    return null;
  }
  const totalSeconds = Math.round(durationMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatQualityLabel(height: number | undefined, isHdr: boolean): string {
  if (!height || !Number.isFinite(height)) {
    return isHdr ? "HDR" : "";
  }
  if (height >= 2160) {
    return isHdr ? "4K HDR" : "4K";
  }
  return isHdr ? `${height}p HDR` : `${height}p`;
}

function formatTypeLabel(type: AssetType): string {
  if (type === "live_photo") {
    return "Live Photo";
  }
  if (type === "video") {
    return "Video";
  }
  return "Photo";
}

function isViewableAsset(asset: ViewerAsset): boolean {
  if (asset.type !== "video") {
    return true;
  }
  return !!asset.ready?.stream;
}

export function ViewerShell({
  contextLabel,
  emptyMessage,
  loadingMessage = "Loading viewer...",
  items,
  status,
  error,
  nextCursor = null,
  previewUrl,
  photoUrl,
  fullPhotoUrl,
  streamUrl,
  liveUrl,
  backLink,
  onClose,
  showFooterNav = true
}: ViewerShellProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedAssetId = searchParams.get("asset");
  const videoContainerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<ReturnType<typeof videojs> | null>(null);
  const liveVideoRef = useRef<HTMLVideoElement | null>(null);
  const topbarRef = useRef<HTMLDivElement | null>(null);
  const hideTimerRef = useRef<number | null>(null);
  const lastInteractionRef = useRef<"keyboard" | "pointer" | null>(null);
  const [isLivePlaying, setIsLivePlaying] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [controlsPinned, setControlsPinned] = useState(false);
  const [durationOverrides, setDurationOverrides] = useState<Record<string, number>>({});
  const [fullPhotoSrc, setFullPhotoSrc] = useState<string | null>(null);

  const viewableItems = useMemo(() => {
    const companionIds = new Set<string>();
    for (const asset of items) {
      if (asset.live_photo_video_id) {
        companionIds.add(asset.live_photo_video_id);
      }
    }
    return items.filter(
      (asset) => !companionIds.has(asset.id) && isViewableAsset(asset)
    );
  }, [items]);

  const paramIndex = useMemo(() => {
    if (!selectedAssetId) {
      return -1;
    }
    return viewableItems.findIndex((asset) => asset.id === selectedAssetId);
  }, [selectedAssetId, viewableItems]);

  const selectedIndex = useMemo(() => {
    if (viewableItems.length === 0) {
      return -1;
    }
    if (paramIndex >= 0) {
      return paramIndex;
    }
    return 0;
  }, [paramIndex, viewableItems.length]);

  useEffect(() => {
    if (viewableItems.length === 0) {
      return;
    }
    if (selectedAssetId && paramIndex >= 0) {
      return;
    }
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("asset", viewableItems[0].id);
        return next;
      },
      { replace: true }
    );
  }, [paramIndex, selectedAssetId, setSearchParams, viewableItems]);

  // zoom UI removed; rely on native browser gestures/zoom.

  useEffect(() => {
    setIsLivePlaying(false);
  }, [selectedAssetId]);

  // Progressive photo loading: show thumbnail first, then swap to full-resolution once loaded.
  useEffect(() => {
    setFullPhotoSrc(null);

    const asset = selectedAssetId ? viewableItems.find((it) => it.id === selectedAssetId) : null;
    if (!asset) {
      return;
    }
    if (asset.type !== "photo" && asset.type !== "live_photo") {
      return;
    }
    if (!fullPhotoUrl) {
      return;
    }

    const fullSrc = fullPhotoUrl(asset.id);
    if (!fullSrc) {
      return;
    }

    let cancelled = false;
    const img = new Image();
    img.decoding = "async";
    img.loading = "eager";

    img.onload = () => {
      if (cancelled) return;
      setFullPhotoSrc(fullSrc);
    };
    img.onerror = () => {
      // Keep thumbnail; ignore.
    };

    // Start download.
    img.src = fullSrc;

    return () => {
      cancelled = true;
      // Best-effort stop.
      img.src = "";
    };
  }, [fullPhotoUrl, selectedAssetId, viewableItems]);

  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const scheduleHide = useCallback(() => {
    clearHideTimer();
    if (controlsPinned) {
      return;
    }
    hideTimerRef.current = window.setTimeout(() => {
      setControlsVisible(false);
    }, CONTROLS_HIDE_DELAY_MS);
  }, [clearHideTimer, controlsPinned]);

  const showControls = useCallback(() => {
    setControlsVisible(true);
    scheduleHide();
  }, [scheduleHide]);

  useEffect(() => {
    setControlsVisible(true);
    scheduleHide();
    return clearHideTimer;
  }, [clearHideTimer, scheduleHide, selectedAssetId]);

  useEffect(() => {
    if (controlsPinned) {
      setControlsVisible(true);
      clearHideTimer();
      return;
    }
    scheduleHide();
  }, [clearHideTimer, controlsPinned, scheduleHide]);

  useEffect(() => {
    const handlePointer = () => {
      lastInteractionRef.current = "pointer";
      showControls();
    };
    const handleKey = () => {
      lastInteractionRef.current = "keyboard";
      showControls();
    };
    window.addEventListener("mousemove", handlePointer);
    window.addEventListener("keydown", handleKey);
    window.addEventListener("touchstart", handlePointer, { passive: true });
    return () => {
      window.removeEventListener("mousemove", handlePointer);
      window.removeEventListener("keydown", handleKey);
      window.removeEventListener("touchstart", handlePointer);
    };
  }, [showControls]);

  useEffect(() => {
    const current = selectedIndex >= 0 ? viewableItems[selectedIndex] : null;
    const isLive = current?.type === "live_photo";
    const hasPair = !!current?.live_photo_video_id;
    const liveReady = !!current?.ready?.live;
    const canPlay = !!liveUrl && isLive && hasPair && liveReady;
    if (!canPlay) {
      setIsLivePlaying(false);
    }
  }, [liveUrl, selectedIndex, viewableItems]);

  const selectIndex = useCallback(
    (nextIndex: number) => {
      if (nextIndex < 0 || nextIndex >= viewableItems.length) {
        return;
      }
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("asset", viewableItems[nextIndex].id);
        return next;
      });
    },
    [setSearchParams, viewableItems]
  );

  const handlePrev = useCallback(() => {
    if (selectedIndex <= 0) {
      return;
    }
    selectIndex(selectedIndex - 1);
  }, [selectIndex, selectedIndex]);

  const handleNext = useCallback(() => {
    if (selectedIndex < 0 || selectedIndex >= viewableItems.length - 1) {
      return;
    }
    selectIndex(selectedIndex + 1);
  }, [selectIndex, selectedIndex, viewableItems.length]);

  useEffect(() => {
    const shouldIgnoreTarget = (target: EventTarget | null) => {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      const tag = target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return true;
      }
      if (target.isContentEditable) {
        return true;
      }
      return false;
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      // Arrow keys should navigate the viewer (bypass the video player),
      // but do not steal keys while typing in inputs.
      if (event.defaultPrevented) {
        return;
      }
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }
      if (shouldIgnoreTarget(event.target)) {
        return;
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        event.stopPropagation();
        handlePrev();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        event.stopPropagation();
        handleNext();
      }
    };

    window.addEventListener("keydown", handleKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", handleKeyDown, { capture: true } as any);
  }, [handleNext, handlePrev]);

  const selectedAsset = selectedIndex >= 0 ? viewableItems[selectedIndex] : null;
  const hasItems = viewableItems.length > 0;
  const isLoading = status === "loading";
  const canPrev = selectedIndex > 0;
  const canNext = selectedIndex >= 0 && selectedIndex < viewableItems.length - 1;
  const isVideo = selectedAsset?.type === "video";
  const isLivePhoto = selectedAsset?.type === "live_photo";
  // zoom removed

  const hasLivePair = !!selectedAsset?.live_photo_video_id;
  const liveReady = !!selectedAsset?.ready?.live;
  const showLiveToggle = !!liveUrl && isLivePhoto && hasLivePair;
  const canPlayLive = showLiveToggle && liveReady;

  const typeLabel = selectedAsset ? formatTypeLabel(selectedAsset.type) : "Asset";
  const dateLabel = selectedAsset ? formatDateLabel(selectedAsset) : "Viewer";
  const resolvedDurationMs = selectedAsset
    ? durationOverrides[selectedAsset.id] ?? selectedAsset.duration_ms
    : null;
  const durationLabel = selectedAsset ? formatDuration(resolvedDurationMs, selectedAsset.type) : null;
  const previewAlt = selectedAsset ? `${typeLabel} preview from ${dateLabel}` : "Viewer preview";
  const videoLabel = selectedAsset ? `${typeLabel} playback from ${dateLabel}` : "Video playback";
  const thumbPhotoSource = selectedAsset
    ? (photoUrl ? photoUrl(selectedAsset.id) : previewUrl(selectedAsset.id))
    : "";
  const photoSource = fullPhotoSrc || thumbPhotoSource;
  const posterSource = selectedAsset ? previewUrl(selectedAsset.id) : "";

  const videoSource = selectedAsset && isVideo ? streamUrl(selectedAsset.id) : "";
  const liveSource = selectedAsset && showLiveToggle ? liveUrl?.(selectedAsset.id) ?? "" : "";

  useEffect(() => {
    if (!selectedAsset || !isVideo) {
      return;
    }
    const container = videoContainerRef.current;
    if (!container) {
      return;
    }
    const source = videoSource;
    if (!source) {
      return;
    }

    container.innerHTML = "";

    const assetId = selectedAsset.id;
    const videoEl = document.createElement("video");
    videoEl.className = "viewer-media-item video-js vjs-default-skin";
    videoEl.setAttribute("controls", "true");
    videoEl.setAttribute("preload", "metadata");
    videoEl.setAttribute("playsinline", "true");
    videoEl.setAttribute("aria-label", videoLabel);
    videoEl.setAttribute("data-stream-src", source);
    if (posterSource) {
      videoEl.setAttribute("poster", posterSource);
    }
    container.appendChild(videoEl);

    const shouldCaptureDuration = !selectedAsset.duration_ms || selectedAsset.duration_ms <= 0;
    const handleDurationUpdate = () => {
      const durationSeconds = videoEl.duration;
      if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
        return;
      }
      const durationMs = Math.round(durationSeconds * 1000);
      setDurationOverrides((prev) => {
        if (prev[assetId] === durationMs) {
          return prev;
        }
        return { ...prev, [assetId]: durationMs };
      });
    };

    if (shouldCaptureDuration) {
      videoEl.addEventListener("loadedmetadata", handleDurationUpdate);
      videoEl.addEventListener("durationchange", handleDurationUpdate);
    }

    // Avoid initializing video.js in unit tests (jsdom doesn't fully support media APIs).
    if (import.meta.env.MODE === "test") {
      return () => {
        if (shouldCaptureDuration) {
          videoEl.removeEventListener("loadedmetadata", handleDurationUpdate);
          videoEl.removeEventListener("durationchange", handleDurationUpdate);
        }
        container.innerHTML = "";
      };
    }

    let cancelled = false;
    let player: ReturnType<typeof videojs> | null = null;

    void (async () => {
      await ensureQualityLevels();
      if (cancelled) {
        return;
      }

      const type = source.includes(".m3u8") ? "application/x-mpegURL" : "video/mp4";

      player = videojs(videoEl, {
        controls: true,
        preload: "metadata",
        playsinline: true,
        fluid: true,
        autoplay: true,
        // Ensure auth cookies are sent for HLS segment/playlist requests.
        html5: {
          vhs: {
            withCredentials: true
          }
        },
        sources: [{ src: source, type }]
      });

      playerRef.current = player;

      // Try to start playback immediately when the viewer opens.
      // (Browsers may block autoplay unless muted; if blocked, this is a no-op.)
      try {
        player.ready(() => {
          const maybePromise = videoEl.play?.();
          if (maybePromise && typeof (maybePromise as Promise<unknown>).catch === "function") {
            (maybePromise as Promise<unknown>).catch(() => {
              // ignore autoplay rejection
            });
          }
        });
      } catch {
        // ignore
      }

      // Add an in-player quality selector next to fullscreen.
      // We rely on videojs-contrib-quality-levels (VHS populates levels for HLS).
      try {
        const controlBar = player.getChild("controlBar") as any;
        const fs = controlBar?.getChild?.("FullscreenToggle") as any;
        const barEl = controlBar?.el?.();
        const fsEl = fs?.el?.();
        const qualityLevels = (player as any).qualityLevels?.();

        if (barEl && fsEl && qualityLevels) {
          const wrapper = document.createElement("div");
          wrapper.className = "vjs-quality-select vjs-control";

          const select = document.createElement("select");
          select.className = "vjs-quality-select-control";
          select.setAttribute("aria-label", "Quality");

          const keepControlsVisible = () => {
            player.addClass("vjs-quality-focus");
            try {
              player.userActive(true);
            } catch {
              // ignore
            }
          };

          const releaseControls = () => {
            player.removeClass("vjs-quality-focus");
          };

          let qualityUiLocked = false;

          const lockQualityUi = () => {
            qualityUiLocked = true;
            keepControlsVisible();
          };

          const unlockQualityUi = () => {
            // Slight delay so Firefox doesn't flap focus during click.
            window.setTimeout(() => {
              qualityUiLocked = false;
              releaseControls();
            }, 150);
          };

          select.addEventListener("focus", lockQualityUi);
          select.addEventListener("blur", unlockQualityUi);
          select.addEventListener("pointerdown", lockQualityUi);
          select.addEventListener("pointerup", lockQualityUi);

          let autoOpt: HTMLOptionElement | null = null;

          const rebuildOptions = () => {
            if (qualityUiLocked) {
              return;
            }
            const previous = select.value || "auto";

            type LevelInfo = {
              index: number;
              height?: number;
              videoRange?: string;
            };

            const levels: LevelInfo[] = [];
            for (let i = 0; i < qualityLevels.length; i += 1) {
              const lvl = qualityLevels[i];
              const videoRange = (lvl as any)?.playlist?.attributes?.["VIDEO-RANGE"]; // HLG/PQ
              levels.push({ index: i, height: lvl?.height, videoRange });
            }

            const sorted = levels
              .filter((lvl) => typeof lvl.height === "number")
              .sort((a, b) => {
                const ha = a.height ?? 0;
                const hb = b.height ?? 0;
                if (ha !== hb) {
                  return ha - hb;
                }
                // SDR before HDR at same res
                const ar = (a.videoRange || "").toUpperCase();
                const br = (b.videoRange || "").toUpperCase();
                return (ar ? 1 : 0) - (br ? 1 : 0);
              });

            select.innerHTML = "";
            autoOpt = document.createElement("option");
            autoOpt.value = "auto";
            autoOpt.textContent = "Auto";
            select.appendChild(autoOpt);

            for (const lvl of sorted) {
              const h = lvl.height as number;
              const vr = (lvl.videoRange || "").toUpperCase();
              const isHdr = !!vr;
              const opt = document.createElement("option");
              opt.value = String(lvl.index);
              opt.textContent = formatQualityLabel(h, isHdr);
              select.appendChild(opt);
            }

            // Restore selection if possible; otherwise default to auto.
            const stillExists = Array.from(select.options).some((opt) => opt.value === previous);
            select.value = stillExists ? previous : "auto";
          };

          const updateAutoLabel = () => {
            if (!autoOpt) {
              return;
            }
            if (qualityUiLocked) {
              return;
            }
            if (select.value !== "auto") {
              autoOpt.textContent = "Auto";
              return;
            }
            try {
              // @ts-expect-error internal VHS bits
              const vhs = (player.tech(true) as any)?.vhs;
              const media = vhs?.playlistController_?.media?.();
              const height = media?.attributes?.RESOLUTION?.height;
              const vr = (media?.attributes?.["VIDEO-RANGE"] || "").toUpperCase();
              if (typeof height === "number") {
                autoOpt.textContent = `Auto (${formatQualityLabel(height, !!vr)})`;
              } else {
                autoOpt.textContent = "Auto";
              }
            } catch {
              autoOpt.textContent = "Auto";
            }
          };

          const applySelection = (value: string) => {
            if (value === "auto") {
              // Default auto: enable SDR levels; keep HDR levels disabled unless user explicitly chooses them.
              for (let i = 0; i < qualityLevels.length; i += 1) {
                const lvl = qualityLevels[i] as any;
                const vr = (lvl?.playlist?.attributes?.["VIDEO-RANGE"] || "").toUpperCase();
                lvl.enabled = !vr;
              }
            } else {
              const targetIndex = Number(value);
              for (let i = 0; i < qualityLevels.length; i += 1) {
                const lvl = qualityLevels[i] as any;
                lvl.enabled = i === targetIndex;
              }
            }

            // Force VHS to start fetching segments for the newly enabled rendition.
            // Without this, previously-buffered segments can continue playing for a while.
            try {
              const t = player.currentTime();
              // @ts-expect-error internal VHS bits
              const vhs = (player.tech(true) as any)?.vhs;
              const loader =
                vhs?.playlistController_?.mainSegmentLoader_ ??
                vhs?.playlistController_?.audioSegmentLoader_;
              loader?.resetEverything?.();
              // Keep playback position.
              player.currentTime(t);
              player.play();
            } catch {
              // Best-effort: seek-to-self to encourage a re-request.
              try {
                const t = player.currentTime();
                player.currentTime(t);
                player.play();
              } catch {
                // ignore
              }
            }
          };

          select.addEventListener("change", () => {
            applySelection(select.value);
            updateAutoLabel();
          });

          rebuildOptions();
          wrapper.appendChild(select);
          barEl.insertBefore(wrapper, fsEl);
          updateAutoLabel();

          // Keep options up-to-date as levels appear.
          // Debounce because VHS can add levels in quick bursts.
          let rebuildTimer: number | null = null;
          const scheduleRebuild = () => {
            if (rebuildTimer !== null) {
              window.clearTimeout(rebuildTimer);
            }
            rebuildTimer = window.setTimeout(() => {
              rebuildOptions();
              updateAutoLabel();
              rebuildTimer = null;
            }, 150);
          };

          if (typeof qualityLevels.on === "function") {
            qualityLevels.on("addqualitylevel", scheduleRebuild);
            qualityLevels.on("removequalitylevel", scheduleRebuild);
          }

          // Update Auto(...) label as VHS switches renditions.
          player.on("timeupdate", updateAutoLabel);
          player.on("loadedmetadata", () => {
            rebuildOptions();
            updateAutoLabel();
          });
        }
      } catch {
        // ignore
      }
    })();

    return () => {
      cancelled = true;
      if (shouldCaptureDuration) {
        videoEl.removeEventListener("loadedmetadata", handleDurationUpdate);
        videoEl.removeEventListener("durationchange", handleDurationUpdate);
      }
      if (player) {
        try {
          player.dispose();
        } catch {
          // ignore
        }
      }
      if (container.contains(videoEl)) {
        container.removeChild(videoEl);
      }
      playerRef.current = null;
    };
  }, [isVideo, posterSource, selectedAsset?.id, videoLabel, videoSource]);

  useEffect(() => {
    const video = liveVideoRef.current;
    if (!video) {
      return;
    }
    if (!isLivePlaying) {
      video.pause();
      try {
        video.currentTime = 0;
      } catch {
        // Ignore seek errors for unbuffered videos.
      }
      return;
    }
    try {
      const playPromise = video.play();
      if (playPromise && typeof (playPromise as Promise<unknown>).catch === "function") {
        (playPromise as Promise<unknown>).catch(() => {
          // ignore autoplay rejection
        });
      }
    } catch {
      // ignore play errors (jsdom or blocked autoplay)
    }
  }, [isLivePlaying, selectedAsset?.id]);

  // Zoom controls removed.

  const handleToggleLive = useCallback(() => {
    if (!canPlayLive) {
      return;
    }
    setIsLivePlaying((prev) => !prev);
  }, [canPlayLive]);

  const handleTopbarFocus = useCallback(() => {
    if (lastInteractionRef.current === "keyboard") {
      setControlsPinned(true);
    }
    setControlsVisible(true);
  }, []);

  const handleTopbarBlur = useCallback(
    (event: FocusEvent<HTMLDivElement>) => {
      const nextTarget = event.relatedTarget as Node | null;
      if (topbarRef.current && nextTarget && topbarRef.current.contains(nextTarget)) {
        return;
      }
      setControlsPinned(false);
    },
    []
  );

  // (quality is displayed in the in-player selector)

  return (
    <section className="page viewer" aria-label={contextLabel}>
      <div className="viewer-stage">
        <div
          ref={topbarRef}
          className={`viewer-topbar${controlsVisible ? " is-visible" : " is-hidden"}`}
          onMouseMove={showControls}
          onFocusCapture={handleTopbarFocus}
          onBlurCapture={handleTopbarBlur}
        >
          <div className="viewer-topbar-left">
            {onClose && (
              <button className="ghost viewer-topbar-button" onClick={onClose}>
                Close
              </button>
            )}
            {backLink && (
              <Link className="ghost viewer-topbar-button" to={backLink.to}>
                {backLink.label}
              </Link>
            )}
            <span className="viewer-topbar-title">{dateLabel}</span>
          </div>
          {showFooterNav && (
            <div className="viewer-topbar-center">
              <span className="viewer-count">
                {selectedIndex >= 0
                  ? `${selectedIndex + 1} of ${viewableItems.length}`
                  : "No assets loaded"}
              </span>
            </div>
          )}
          {showFooterNav && (
            <div className="viewer-topbar-right">
              {showLiveToggle && (
                <>
                  <button
                    className="ghost viewer-topbar-button"
                    onClick={handleToggleLive}
                    disabled={!canPlayLive}
                    aria-pressed={isLivePlaying}
                  >
                    {isLivePlaying ? "Stop Live" : "Play Live"}
                  </button>
                  {!canPlayLive && (
                    <span className="hint viewer-live-hint">Live video processing</span>
                  )}
                </>
              )}
              {/* Prev/Next buttons removed: hover arrows + keyboard arrows handle navigation. */}
            </div>
          )}
        </div>
        <div className={`viewer-media${isVideo ? " is-video" : ""}${controlsVisible ? " controls-visible" : " controls-hidden"}`}>
          {error && (
            <div className="status error viewer-status" role="alert">
              {error}
            </div>
          )}
          {isLoading && !hasItems && (
            <div className="viewer-placeholder" role="status">
              {loadingMessage}
            </div>
          )}
          {!isLoading && !hasItems && !error && (
            <div className="viewer-placeholder" role="status">
              {emptyMessage}
            </div>
          )}
          {selectedAsset && (
            <>
              {isVideo ? (
                <div ref={videoContainerRef} className="viewer-media-video" />
              ) : isLivePhoto ? (
                <div className={`viewer-live-photo${isLivePlaying ? " is-playing" : ""}`}>
                  <img
                    className="viewer-media-item viewer-media-photo viewer-live-still"
                    src={photoSource}
                    alt={previewAlt}
                  />
                  {showLiveToggle && liveReady && (
                    <video
                      ref={liveVideoRef}
                      key={`${selectedAsset.id}-live`}
                      className={`viewer-media-item viewer-live-video${isLivePlaying ? " is-playing" : ""}`}
                      muted
                      playsInline
                      loop
                      preload="metadata"
                      src={liveSource}
                      aria-hidden="true"
                    />
                  )}
                </div>
              ) : (
                <img
                  className="viewer-media-item viewer-media-photo"
                  src={photoSource}
                  alt={previewAlt}
                />
              )}
              {/* type/duration pills intentionally not shown in viewer */}
            </>
          )}
          <div className="viewer-hover-nav">
            <button
              className="viewer-arrow ghost prev"
              onClick={handlePrev}
              disabled={!canPrev}
              aria-label="Previous asset"
            >
              <span aria-hidden="true">&lt;</span>
            </button>
            <button
              className="viewer-arrow ghost next"
              onClick={handleNext}
              disabled={!canNext}
              aria-label="Next asset"
            >
              <span aria-hidden="true">&gt;</span>
            </button>
          </div>
        </div>
        {nextCursor && hasItems && (
          <p className="hint viewer-next-hint">More assets are available in the timeline.</p>
        )}
      </div>
    </section>
  );
}
