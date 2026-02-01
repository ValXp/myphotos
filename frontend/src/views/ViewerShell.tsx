import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import videojs from "video.js";
import "video.js/dist/video-js.css";
import "videojs-contrib-quality-levels";
import "videojs-http-source-selector";

const ZOOM_LEVELS = [1, 1.5, 2, 3];
const DEFAULT_ZOOM_INDEX = 0;

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC"
});
const timeFormatter = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
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
  streamUrl: (assetId: string) => string;
  backLink?: {
    to: string;
    label: string;
  };
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

function formatTimeLabel(asset: ViewerAsset): string | null {
  const timestamp = assetTimestamp(asset);
  if (!timestamp) {
    return null;
  }
  return timeFormatter.format(timestamp);
}

function formatDimensions(asset: ViewerAsset): string | null {
  if (!asset.width || !asset.height) {
    return null;
  }
  return `${asset.width} x ${asset.height}`;
}

function formatDuration(durationMs: number | null): string | null {
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

function formatTypeLabel(type: AssetType): string {
  if (type === "live_photo") {
    return "Live Photo";
  }
  if (type === "video") {
    return "Video";
  }
  return "Photo";
}

export function ViewerShell({
  contextLabel,
  emptyMessage,
  emptySubhead,
  loadingMessage = "Loading viewer...",
  items,
  status,
  error,
  nextCursor = null,
  previewUrl,
  photoUrl,
  streamUrl,
  backLink,
  showFooterNav = true
}: ViewerShellProps) {
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedAssetId = searchParams.get("asset");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playerRef = useRef<ReturnType<typeof videojs> | null>(null);

  const paramIndex = useMemo(() => {
    if (!selectedAssetId) {
      return -1;
    }
    return items.findIndex((asset) => asset.id === selectedAssetId);
  }, [items, selectedAssetId]);

  const selectedIndex = useMemo(() => {
    if (items.length === 0) {
      return -1;
    }
    if (paramIndex >= 0) {
      return paramIndex;
    }
    return 0;
  }, [items.length, paramIndex]);

  useEffect(() => {
    if (items.length === 0) {
      return;
    }
    if (selectedAssetId && paramIndex >= 0) {
      return;
    }
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("asset", items[0].id);
        return next;
      },
      { replace: true }
    );
  }, [items, paramIndex, selectedAssetId, setSearchParams]);

  useEffect(() => {
    setZoomIndex(DEFAULT_ZOOM_INDEX);
  }, [selectedAssetId]);

  const selectIndex = useCallback(
    (nextIndex: number) => {
      if (nextIndex < 0 || nextIndex >= items.length) {
        return;
      }
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("asset", items[nextIndex].id);
        return next;
      });
    },
    [items, setSearchParams]
  );

  const handlePrev = useCallback(() => {
    if (selectedIndex <= 0) {
      return;
    }
    selectIndex(selectedIndex - 1);
  }, [selectIndex, selectedIndex]);

  const handleNext = useCallback(() => {
    if (selectedIndex < 0 || selectedIndex >= items.length - 1) {
      return;
    }
    selectIndex(selectedIndex + 1);
  }, [selectIndex, selectedIndex, items.length]);

  const selectedAsset = selectedIndex >= 0 ? items[selectedIndex] : null;
  const hasItems = items.length > 0;
  const isLoading = status === "loading";
  const canPrev = selectedIndex > 0;
  const canNext = selectedIndex >= 0 && selectedIndex < items.length - 1;
  const isVideo = selectedAsset?.type === "video";
  const isZoomable = !!selectedAsset && !isVideo;
  const zoom = ZOOM_LEVELS[zoomIndex] ?? ZOOM_LEVELS[DEFAULT_ZOOM_INDEX];
  const canZoomIn = isZoomable && zoomIndex < ZOOM_LEVELS.length - 1;
  const canZoomOut = isZoomable && zoomIndex > 0;
  const canResetZoom = isZoomable && zoomIndex !== DEFAULT_ZOOM_INDEX;
  const zoomLabel = `${Math.round(zoom * 100)}%`;

  const typeLabel = selectedAsset ? formatTypeLabel(selectedAsset.type) : "Asset";
  const dateLabel = selectedAsset ? formatDateLabel(selectedAsset) : "Viewer";
  const timeLabel = selectedAsset ? formatTimeLabel(selectedAsset) : null;
  const dimensionLabel = selectedAsset ? formatDimensions(selectedAsset) : null;
  const durationLabel = selectedAsset ? formatDuration(selectedAsset.duration_ms) : null;
  const detailParts = [timeLabel, dimensionLabel, durationLabel].filter(
    (value): value is string => !!value
  );
  const detailLine = detailParts.length > 0 ? detailParts.join(" | ") : "Details unavailable.";
  const previewAlt = selectedAsset ? `${typeLabel} preview from ${dateLabel}` : "Viewer preview";
  const videoLabel = selectedAsset ? `${typeLabel} playback from ${dateLabel}` : "Video playback";
  const photoSource = selectedAsset
    ? (photoUrl ? photoUrl(selectedAsset.id) : previewUrl(selectedAsset.id))
    : "";

  const videoSource = selectedAsset && isVideo ? streamUrl(selectedAsset.id) : "";

  useEffect(() => {
    if (!selectedAsset || !isVideo) {
      return;
    }
    const element = videoRef.current;
    if (!element) {
      return;
    }

    // Avoid initializing video.js in unit tests (jsdom doesn't fully support media APIs).
    if (import.meta.env.MODE === "test") {
      return;
    }

    // Dispose any previous player (asset switch / unmount).
    if (playerRef.current) {
      try {
        playerRef.current.dispose();
      } catch {
        // ignore
      }
      playerRef.current = null;
    }

    const source = videoSource;
    if (!source) {
      return;
    }

    // Ensure the element has the video.js class.
    element.classList.add("video-js");
    element.classList.add("vjs-default-skin");

    const type = source.includes(".m3u8") ? "application/x-mpegURL" : "video/mp4";

    const player = videojs(element, {
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
        const el = element as HTMLVideoElement;
        const maybePromise = el.play?.();
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

        const rebuildOptions = () => {
          const levels: Array<{ index: number; height?: number }> = [];
          for (let i = 0; i < qualityLevels.length; i += 1) {
            const lvl = qualityLevels[i];
            levels.push({ index: i, height: lvl?.height });
          }
          // unique + sort by height
          const unique = new Map<number, number>();
          for (const lvl of levels) {
            if (typeof lvl.height === "number" && !unique.has(lvl.height)) {
              unique.set(lvl.height, lvl.index);
            }
          }
          const heights = Array.from(unique.keys()).sort((a, b) => a - b);

          select.innerHTML = "";
          const autoOpt = document.createElement("option");
          autoOpt.value = "auto";
          autoOpt.textContent = "Auto";
          select.appendChild(autoOpt);
          for (const h of heights) {
            const opt = document.createElement("option");
            opt.value = String(h);
            opt.textContent = `${h}p`;
            select.appendChild(opt);
          }
        };

        const applySelection = (value: string) => {
          if (value === "auto") {
            for (let i = 0; i < qualityLevels.length; i += 1) {
              qualityLevels[i].enabled = true;
            }
          } else {
            const targetH = Number(value);
            for (let i = 0; i < qualityLevels.length; i += 1) {
              const lvl = qualityLevels[i];
              lvl.enabled = lvl?.height === targetH;
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
        });

        rebuildOptions();
        wrapper.appendChild(select);
        barEl.insertBefore(wrapper, fsEl);

        // Keep options up-to-date as levels appear.
        if (typeof qualityLevels.on === "function") {
          qualityLevels.on("addqualitylevel", rebuildOptions);
          qualityLevels.on("removequalitylevel", rebuildOptions);
        }
      }
    } catch {
      // ignore
    }

    return () => {
      try {
        player.dispose();
      } catch {
        // ignore
      }
      playerRef.current = null;
    };
  }, [isVideo, selectedAsset, videoSource]);

  const handleZoomIn = useCallback(() => {
    setZoomIndex((index) => Math.min(index + 1, ZOOM_LEVELS.length - 1));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoomIndex((index) => Math.max(index - 1, 0));
  }, []);

  const handleZoomReset = useCallback(() => {
    setZoomIndex(DEFAULT_ZOOM_INDEX);
  }, []);

  const [qualityLabel, setQualityLabel] = useState<string | null>(null);

  return (
    <section className="page viewer">
      <div className="viewer-stage">
        {error && (
          <div className="status error" role="alert">
            {error}
          </div>
        )}
        <div className={`viewer-media${isVideo ? " is-video" : ""}`}>
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
                <video
                  ref={videoRef}
                  key={selectedAsset.id}
                  className="viewer-media-item"
                  controls
                  preload="metadata"
                  playsInline
                  poster={previewUrl(selectedAsset.id)}
                  aria-label={videoLabel}
                  data-stream-src={videoSource}
                />
              ) : (
                <img
                  className={`viewer-media-item viewer-media-photo${zoomIndex > 0 ? " is-zoomed" : ""}`}
                  src={photoSource}
                  alt={previewAlt}
                  style={{ transform: `scale(${zoom})` }}
                />
              )}
              <span className="viewer-badge">{typeLabel}</span>
              {durationLabel && <span className="viewer-duration">{durationLabel}</span>}
            </>
          )}
          <div className="viewer-hover-nav" aria-hidden="true">
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
        {showFooterNav && (
          <div className="viewer-controls">
            <div className="viewer-nav">
              <button className="ghost" onClick={handlePrev} disabled={!canPrev}>
                Prev
              </button>
              <div className="viewer-count">
                {selectedIndex >= 0 ? `${selectedIndex + 1} of ${items.length}` : "No assets loaded"}
              </div>
              <button className="ghost" onClick={handleNext} disabled={!canNext}>
                Next
              </button>
            </div>
            <div className="viewer-zoom">
              <span className="viewer-zoom-label">Zoom</span>
              <div className="viewer-zoom-buttons">
                <button
                  className="ghost viewer-zoom-btn"
                  onClick={handleZoomOut}
                  disabled={!canZoomOut}
                  aria-label="Zoom out"
                >
                  -
                </button>
                <span className="viewer-zoom-value" aria-live="polite">
                  {zoomLabel}
                </span>
                <button
                  className="ghost viewer-zoom-btn"
                  onClick={handleZoomIn}
                  disabled={!canZoomIn}
                  aria-label="Zoom in"
                >
                  +
                </button>
                <button
                  className="ghost viewer-zoom-btn"
                  onClick={handleZoomReset}
                  disabled={!canResetZoom}
                  aria-label="Reset zoom"
                >
                  Fit
                </button>
              </div>
            </div>
            {/* Quality selector rendered in the meta panel so it also shows when footer nav is hidden. */}
          </div>
        )}
        {nextCursor && hasItems && (
          <p className="hint">More assets are available in the timeline.</p>
        )}
      </div>
      <div className="viewer-meta">
        <p className="eyebrow">{contextLabel}</p>
        <h1>{dateLabel}</h1>
        <p className="subhead">
          {selectedAsset ? `${typeLabel} | ${detailLine}` : emptySubhead}
        </p>
        <div className="pill-group">
          <span className="pill">{typeLabel}</span>
          {selectedIndex >= 0 && <span className="pill">{selectedIndex + 1} of {items.length}</span>}
          {selectedAsset?.live_photo_video_id && <span className="pill">Live pairing</span>}
        </div>

        {/* Quality selector is rendered by video.js in the player control bar. */}
        {backLink && (
          <Link className="ghost" to={backLink.to}>
            {backLink.label}
          </Link>
        )}
      </div>
    </section>
  );
}
