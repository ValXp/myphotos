import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import Hls from "hls.js";
import { Link, useSearchParams } from "react-router-dom";

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
  const hlsRef = useRef<Hls | null>(null);
  const [hlsLevels, setHlsLevels] = useState<Array<{
    index: number;
    width?: number;
    height?: number;
    bitrate?: number;
  }>>([]);
  const [hlsLevelIndex, setHlsLevelIndex] = useState<number>(-1); // -1 = auto

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

    // Reset between selections.
    // jsdom doesn't implement pause/load, so guard for tests.
    if (typeof element.pause === "function") {
      try {
        element.pause();
      } catch {
        // ignore
      }
    }
    element.removeAttribute("src");
    if (typeof element.load === "function") {
      try {
        element.load();
      } catch {
        // ignore
      }
    }

    const source = videoSource;
    if (!source) {
      return;
    }

    // HLS: Firefox (and most non-Safari browsers) need hls.js.
    if (source.includes(".m3u8")) {
      const canNativeHls =
        typeof element.canPlayType === "function" &&
        element.canPlayType("application/vnd.apple.mpegurl") !== "";

      if (canNativeHls) {
        element.src = source;
        return;
      }

      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: true,
          lowLatencyMode: false
        });
        hlsRef.current = hls;
        hls.loadSource(source);
        hls.attachMedia(element);

        const syncLevels = () => {
          const levels = hls.levels.map((level, index) => ({
            index,
            width: level.width,
            height: level.height,
            bitrate: level.bitrate
          }));
          setHlsLevels(levels);
        };

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          syncLevels();
          // -1 represents auto in hls.js
          setHlsLevelIndex(hls.currentLevel);
        });

        hls.on(Hls.Events.LEVEL_SWITCHED, (_event, data) => {
          if (typeof data?.level === "number") {
            setHlsLevelIndex(data.level);
          }
        });

        return () => {
          hlsRef.current = null;
          setHlsLevels([]);
          setHlsLevelIndex(-1);
          hls.destroy();
        };
      }

      // No HLS support.
      element.src = source;
      return;
    }

    // Progressive fallback.
    element.src = source;
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

  const sortedHlsLevels = useMemo(() => {
    return [...hlsLevels].sort((a, b) => (a.height ?? 0) - (b.height ?? 0));
  }, [hlsLevels]);

  const selectedHlsLabel = useMemo(() => {
    if (!sortedHlsLevels.length) {
      return null;
    }
    const level = sortedHlsLevels.find((candidate) => candidate.index === hlsLevelIndex);
    if (!level) {
      return hlsLevelIndex === -1 ? "Auto" : `Level ${hlsLevelIndex}`;
    }
    const res = level.height ? `${level.height}p` : "Unknown";
    const bitrate = level.bitrate ? `${Math.round(level.bitrate / 1000)} kbps` : null;
    return bitrate ? `${res} · ${bitrate}` : res;
  }, [hlsLevelIndex, sortedHlsLevels]);

  const handleHlsLevelChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    const value = Number(event.target.value);
    const hls = hlsRef.current;
    setHlsLevelIndex(value);
    if (hls) {
      // -1 = auto; otherwise index of hls.levels
      hls.currentLevel = value;
    }
  }, []);

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

        {isVideo && sortedHlsLevels.length > 0 && (
          <div className="viewer-zoom" role="group" aria-label="Video quality">
            <span className="viewer-zoom-label">Quality</span>
            <div className="viewer-zoom-buttons">
              <select
                className="text-input"
                value={hlsLevelIndex}
                onChange={handleHlsLevelChange}
                aria-label="Select video quality"
              >
                <option value={-1}>Auto</option>
                {sortedHlsLevels.map((level) => {
                  const label = level.height
                    ? `${level.height}p${level.bitrate ? ` (${Math.round(level.bitrate / 1000)} kbps)` : ""}`
                    : `Level ${level.index}`;
                  return (
                    <option key={level.index} value={level.index}>
                      {label}
                    </option>
                  );
                })}
              </select>
              {selectedHlsLabel && <span className="viewer-zoom-value">{selectedHlsLabel}</span>}
            </div>
          </div>
        )}
        {backLink && (
          <Link className="ghost" to={backLink.to}>
            {backLink.label}
          </Link>
        )}
      </div>
    </section>
  );
}
