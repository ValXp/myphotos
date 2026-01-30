import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const PAGE_SIZE = 200;
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

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type AssetType = "photo" | "video" | "live_photo";

type AssetSummary = {
  id: string;
  type: AssetType;
  captured_at: string | null;
  created_at: string | null;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  live_photo_video_id: string | null;
};

type AssetsResponse = {
  items: AssetSummary[];
  next_cursor: string | null;
};

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(buildApiUrl(path), {
    ...options,
    headers,
    credentials: "include"
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`.trim();
    try {
      const data = await response.json();
      if (data && typeof data === "object" && "detail" in data && typeof data.detail === "string") {
        message = data.detail;
      }
    } catch (error) {
      // Ignore JSON parsing errors and keep the fallback message.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

function assetTimestamp(asset: AssetSummary): Date | null {
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

function formatDateLabel(asset: AssetSummary): string {
  const timestamp = assetTimestamp(asset);
  if (!timestamp) {
    return "Unknown date";
  }
  return dateFormatter.format(timestamp);
}

function formatTimeLabel(asset: AssetSummary): string | null {
  const timestamp = assetTimestamp(asset);
  if (!timestamp) {
    return null;
  }
  return timeFormatter.format(timestamp);
}

function formatDimensions(asset: AssetSummary): string | null {
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

function previewUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/thumb`);
}

function streamUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/stream`);
}

async function fetchAssets(): Promise<AssetsResponse> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  return requestJson<AssetsResponse>(`/assets?${params.toString()}`, { method: "GET" });
}

export function ViewerView() {
  const { refreshSession } = useAuth();
  const [items, setItems] = useState<AssetSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedAssetId = searchParams.get("asset");

  const loadAssets = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const data = await fetchAssets();
      setItems(data.items);
      setNextCursor(data.next_cursor ?? null);
      setStatus("ready");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load assets.";
      setError(message);
      setStatus("error");
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    }
  }, [refreshSession]);

  useEffect(() => {
    void loadAssets();
  }, [loadAssets]);

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
    setSearchParams({ asset: items[0].id }, { replace: true });
  }, [items, paramIndex, selectedAssetId, setSearchParams]);

  useEffect(() => {
    setZoomIndex(DEFAULT_ZOOM_INDEX);
  }, [selectedAssetId]);

  const selectIndex = useCallback(
    (nextIndex: number) => {
      if (nextIndex < 0 || nextIndex >= items.length) {
        return;
      }
      setSearchParams({ asset: items[nextIndex].id });
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

  const handleZoomIn = useCallback(() => {
    setZoomIndex((index) => Math.min(index + 1, ZOOM_LEVELS.length - 1));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoomIndex((index) => Math.max(index - 1, 0));
  }, []);

  const handleZoomReset = useCallback(() => {
    setZoomIndex(DEFAULT_ZOOM_INDEX);
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
              Loading viewer...
            </div>
          )}
          {!isLoading && !hasItems && !error && (
            <div className="viewer-placeholder" role="status">
              No assets yet. Add photos or videos to start viewing.
            </div>
          )}
          {selectedAsset && (
            <>
              {isVideo ? (
                <video
                  key={selectedAsset.id}
                  className="viewer-media-item"
                  controls
                  preload="metadata"
                  playsInline
                  poster={previewUrl(selectedAsset.id)}
                  src={streamUrl(selectedAsset.id)}
                  aria-label={videoLabel}
                />
              ) : (
                <img
                  className={`viewer-media-item viewer-media-photo${zoomIndex > 0 ? " is-zoomed" : ""}`}
                  src={previewUrl(selectedAsset.id)}
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
        </div>
        {nextCursor && hasItems && (
          <p className="hint">More assets are available in the timeline.</p>
        )}
      </div>
      <div className="viewer-meta">
        <p className="eyebrow">Owner viewer</p>
        <h1>{dateLabel}</h1>
        <p className="subhead">
          {selectedAsset ? `${typeLabel} | ${detailLine}` : "Pick an asset from the timeline."}
        </p>
        <div className="pill-group">
          <span className="pill">{typeLabel}</span>
          {selectedIndex >= 0 && <span className="pill">{selectedIndex + 1} of {items.length}</span>}
          {selectedAsset?.live_photo_video_id && <span className="pill">Live pairing</span>}
        </div>
        <Link className="ghost" to="/app/timeline">
          Back to timeline
        </Link>
      </div>
    </section>
  );
}
