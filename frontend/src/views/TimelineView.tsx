import type { ChangeEvent, CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useLivePhotoHover } from "../hooks/useLivePhotoHover";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const PAGE_SIZE = 60;
const THUMB_PROFILE = "thumb_md";

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

type AlbumSummary = {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  item_count: number;
};

type AlbumsResponse = {
  items: AlbumSummary[];
};

type AlbumItemsResponse = {
  added: string[];
  skipped: string[];
  item_count: number;
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

function thumbnailUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/thumb?profile=${THUMB_PROFILE}`);
}

function liveVideoUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/live`);
}

async function fetchAssets(cursor: string | null): Promise<AssetsResponse> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) {
    params.set("cursor", cursor);
  }
  return requestJson<AssetsResponse>(`/assets?${params.toString()}`, { method: "GET" });
}

export function TimelineView() {
  const { refreshSession } = useAuth();
  const [items, setItems] = useState<AssetSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "loading-more" | "error">(
    "idle"
  );
  const [error, setError] = useState<string | null>(null);
  const [albums, setAlbums] = useState<AlbumSummary[]>([]);
  const [albumStatus, setAlbumStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [albumError, setAlbumError] = useState<string | null>(null);
  const [selectedAlbumId, setSelectedAlbumId] = useState<string>("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [actionStatus, setActionStatus] = useState<"idle" | "working" | "success" | "error">("idle");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const inFlightRef = useRef(false);
  const { registerVideoRef, handleMouseEnter, handleMouseLeave } = useLivePhotoHover();

  const loadAssets = useCallback(
    async (cursor: string | null, mode: "initial" | "more") => {
      if (inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      setError(null);
      setStatus(mode === "initial" ? "loading" : "loading-more");
      if (mode === "initial") {
        setItems([]);
        setNextCursor(null);
        setSelectedIds(new Set());
        setActionStatus("idle");
        setActionMessage(null);
      }
      try {
        const data = await fetchAssets(cursor);
        setItems((prev) => (mode === "initial" ? data.items : [...prev, ...data.items]));
        setNextCursor(data.next_cursor ?? null);
        setStatus("ready");
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unable to load timeline.";
        setError(message);
        setStatus("error");
        if (err instanceof ApiError && err.status === 401) {
          await refreshSession();
        }
      } finally {
        inFlightRef.current = false;
      }
    },
    [refreshSession]
  );

  const loadAlbums = useCallback(async () => {
    setAlbumStatus("loading");
    setAlbumError(null);
    try {
      const data = await requestJson<AlbumsResponse>("/albums", { method: "GET" });
      setAlbums(data.items);
      setAlbumStatus("ready");
      setSelectedAlbumId((prev) => {
        if (data.items.length === 0) {
          return "";
        }
        if (prev && data.items.some((album) => album.id === prev)) {
          return prev;
        }
        return data.items[0].id;
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load albums.";
      setAlbumError(message);
      setAlbumStatus("error");
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    }
  }, [refreshSession]);

  const toggleSelection = useCallback((assetId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(assetId)) {
        next.delete(assetId);
      } else {
        next.add(assetId);
      }
      return next;
    });
    setActionStatus("idle");
    setActionMessage(null);
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedIds(new Set(items.map((asset) => asset.id)));
    setActionStatus("idle");
    setActionMessage(null);
  }, [items]);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
    setActionStatus("idle");
    setActionMessage(null);
  }, []);

  const handleAlbumChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    setSelectedAlbumId(event.target.value);
    setActionStatus("idle");
    setActionMessage(null);
  }, []);

  const handleAddToAlbum = useCallback(async () => {
    if (!selectedAlbumId || selectedIds.size === 0) {
      return;
    }
    setIsAdding(true);
    setActionStatus("working");
    setActionMessage(null);
    try {
      const response = await requestJson<AlbumItemsResponse>(`/albums/${selectedAlbumId}/items`, {
        method: "POST",
        body: JSON.stringify({ asset_ids: Array.from(selectedIds) })
      });
      const addedCount = response.added.length;
      const skippedCount = response.skipped.length;
      let message = "No assets were added.";
      if (addedCount > 0) {
        message = `Added ${addedCount} asset${addedCount === 1 ? "" : "s"} to album.`;
        if (skippedCount > 0) {
          message += ` ${skippedCount} already in album.`;
        }
      } else if (skippedCount > 0) {
        message = "Selected assets are already in that album.";
      }
      const updatedAt = addedCount > 0 ? new Date().toISOString() : null;
      setActionStatus("success");
      setActionMessage(message);
      setSelectedIds(new Set());
      setAlbums((prev) =>
        prev.map((album) =>
          album.id === selectedAlbumId
            ? {
                ...album,
                item_count: response.item_count,
                updated_at: updatedAt ?? album.updated_at
              }
            : album
        )
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to add items to album.";
      setActionStatus("error");
      setActionMessage(message);
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    } finally {
      setIsAdding(false);
    }
  }, [refreshSession, selectedAlbumId, selectedIds]);

  const handleRefresh = useCallback(() => {
    void loadAssets(null, "initial");
    void loadAlbums();
  }, [loadAssets, loadAlbums]);

  const handleLoadMore = useCallback(() => {
    if (!nextCursor) {
      return;
    }
    void loadAssets(nextCursor, "more");
  }, [loadAssets, nextCursor]);

  useEffect(() => {
    void loadAssets(null, "initial");
  }, [loadAssets]);

  useEffect(() => {
    void loadAlbums();
  }, [loadAlbums]);

  useEffect(() => {
    if (!nextCursor) {
      return;
    }
    if (status === "loading" || status === "loading-more") {
      return;
    }
    if (typeof window === "undefined" || !("IntersectionObserver" in window)) {
      return;
    }
    const target = sentinelRef.current;
    if (!target) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadAssets(nextCursor, "more");
        }
      },
      { rootMargin: "240px" }
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [loadAssets, nextCursor, status]);

  const hasItems = items.length > 0;
  const isLoading = status === "loading";
  const isLoadingMore = status === "loading-more";
  const selectedCount = selectedIds.size;
  const hasAlbums = albums.length > 0;
  const isAlbumLoading = albumStatus === "loading";
  const isActionError = actionStatus === "error";
  const isActionSuccess = actionStatus === "success";

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Owner timeline</p>
          <h1>Timeline</h1>
          <p className="subhead">
            Newest-first moments with infinite scroll. Thumbnails load on demand to keep originals
            offline.
          </p>
        </div>
        <div className="timeline-actions">
          <div className="pill-group">
            <span className="pill">{items.length} loaded</span>
            <span className="pill">Newest first</span>
            <span className="pill">{selectedCount} selected</span>
          </div>
          <div className="selection-tools">
            <button className="ghost" onClick={handleSelectAll} disabled={!hasItems}>
              Select all
            </button>
            <button className="ghost" onClick={handleClearSelection} disabled={selectedCount === 0}>
              Clear
            </button>
          </div>
          <div className="album-picker">
            <select
              className="text-input"
              value={selectedAlbumId}
              onChange={handleAlbumChange}
              disabled={!hasAlbums || isAlbumLoading}
              aria-label="Select album"
            >
              {!hasAlbums && <option value="">No albums yet</option>}
              {hasAlbums &&
                albums.map((album) => (
                  <option key={album.id} value={album.id}>
                    {album.title || "Untitled album"}
                  </option>
                ))}
            </select>
            <button
              className="primary"
              onClick={handleAddToAlbum}
              disabled={!hasAlbums || selectedCount === 0 || isAdding || isAlbumLoading}
            >
              Add to album
            </button>
          </div>
          <button className="ghost" onClick={handleRefresh} disabled={isLoading || isAdding}>
            Refresh
          </button>
        </div>
      </header>
      {actionMessage && (
        <div
          className={`status${isActionError ? " error" : ""}${isActionSuccess ? " success" : ""}`}
          role={isActionError ? "alert" : "status"}
        >
          {actionMessage}
        </div>
      )}
      {albumError && (
        <div className="status error" role="alert">
          {albumError}
        </div>
      )}
      {error && (
        <div className="status error" role="alert">
          {error}
        </div>
      )}
      {isLoading && !hasItems && (
        <div className="status" role="status">
          Loading timeline...
        </div>
      )}
      {!isLoading && !hasItems && !error && (
        <div className="status" role="status">
          No assets yet. Add photos or videos to a watched folder to populate the timeline.
        </div>
      )}
      {hasItems && (
        <div className="grid timeline-grid stagger">
          {items.map((asset, index) => {
            const dateLabel = formatDateLabel(asset);
            const timeLabel = formatTimeLabel(asset);
            const dimensionLabel = formatDimensions(asset);
            const durationLabel = formatDuration(asset.duration_ms);
            const metaParts = [timeLabel, dimensionLabel, durationLabel].filter(
              (value): value is string => !!value
            );
            const typeLabel = formatTypeLabel(asset.type);
            const thumbAlt = `${typeLabel} thumbnail from ${dateLabel}`;
            const isSelected = selectedIds.has(asset.id);
            const isLivePhoto = asset.type === "live_photo" && !!asset.live_photo_video_id;
            const livePreviewSrc = isLivePhoto ? liveVideoUrl(asset.id) : null;

            return (
              <article
                key={asset.id}
                className={`media-card timeline-card${isSelected ? " is-selected" : ""}`}
                style={{ "--delay": `${index * 0.04}s` } as CSSProperties}
              >
                <div
                  className={`media-thumb${isLivePhoto ? " live-photo-thumb" : ""}`}
                  onMouseEnter={isLivePhoto ? () => handleMouseEnter(asset.id) : undefined}
                  onMouseLeave={isLivePhoto ? () => handleMouseLeave(asset.id) : undefined}
                >
                  <label className="media-select">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelection(asset.id)}
                      aria-label={isSelected ? "Deselect asset" : "Select asset"}
                    />
                  </label>
                  <img
                    className={isLivePhoto ? "live-photo-still" : undefined}
                    src={thumbnailUrl(asset.id)}
                    alt={thumbAlt}
                    loading="lazy"
                  />
                  {isLivePhoto && (
                    <video
                      ref={registerVideoRef(asset.id)}
                      className="live-photo-video"
                      muted
                      playsInline
                      preload="metadata"
                      loop
                      src={livePreviewSrc ?? undefined}
                      aria-hidden="true"
                      onError={(event) => {
                        event.currentTarget.dataset.failed = "true";
                      }}
                    />
                  )}
                  <span className="media-badge">{typeLabel}</span>
                  {durationLabel && <span className="media-duration">{durationLabel}</span>}
                </div>
                <div className="media-meta">
                  <h3>{dateLabel}</h3>
                  {metaParts.length > 0 && <p>{metaParts.join(" · ")}</p>}
                </div>
              </article>
            );
          })}
        </div>
      )}
      <div className="timeline-footer">
        {isLoadingMore && <p className="hint">Loading more...</p>}
        {!isLoadingMore && nextCursor && (
          <button className="ghost" onClick={handleLoadMore}>
            Load more
          </button>
        )}
        {!nextCursor && hasItems && <p className="hint">End of timeline.</p>}
        <div className="timeline-sentinel" ref={sentinelRef} aria-hidden="true" />
      </div>
    </section>
  );
}
