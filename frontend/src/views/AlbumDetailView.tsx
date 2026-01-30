import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useLivePhotoHover } from "../hooks/useLivePhotoHover";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
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

type AlbumSummary = {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  item_count: number;
};

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

type AlbumAssetsResponse = {
  items: AssetSummary[];
};

type AlbumItemsRemoveResponse = {
  removed: string[];
  missing: string[];
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

function parseDate(value: string | null): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function formatAlbumUpdated(album: AlbumSummary): string {
  const date = parseDate(album.updated_at ?? album.created_at);
  if (!date) {
    return "Updated date unavailable";
  }
  return `Updated ${dateFormatter.format(date)}`;
}

function formatItemCount(count: number): string {
  return `${count} item${count === 1 ? "" : "s"}`;
}

function assetTimestamp(asset: AssetSummary): Date | null {
  return parseDate(asset.captured_at ?? asset.created_at);
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

export function AlbumDetailView() {
  const { albumId } = useParams();
  const { refreshSession } = useAuth();
  const [album, setAlbum] = useState<AlbumSummary | null>(null);
  const [items, setItems] = useState<AssetSummary[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [actionStatus, setActionStatus] = useState<"idle" | "working" | "success" | "error">("idle");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [isRemoving, setIsRemoving] = useState(false);
  const { registerVideoRef, handleMouseEnter, handleMouseLeave } = useLivePhotoHover();

  const loadAlbum = useCallback(async () => {
    if (!albumId) {
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const [albumData, assetsData] = await Promise.all([
        requestJson<AlbumSummary>(`/albums/${albumId}`, { method: "GET" }),
        requestJson<AlbumAssetsResponse>(`/albums/${albumId}/assets`, { method: "GET" })
      ]);
      setAlbum(albumData);
      setItems(assetsData.items);
      setStatus("ready");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load album.";
      setError(message);
      setStatus("error");
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    }
  }, [albumId, refreshSession]);

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

  const handleRemoveSelected = useCallback(async () => {
    if (!albumId || selectedIds.size === 0) {
      return;
    }
    setIsRemoving(true);
    setActionStatus("working");
    setActionMessage(null);
    try {
      const response = await requestJson<AlbumItemsRemoveResponse>(`/albums/${albumId}/items`, {
        method: "DELETE",
        body: JSON.stringify({ asset_ids: Array.from(selectedIds) })
      });
      const removedCount = response.removed.length;
      const missingCount = response.missing.length;
      let message = "No assets were removed.";
      if (removedCount > 0) {
        message = `Removed ${removedCount} asset${removedCount === 1 ? "" : "s"} from album.`;
        if (missingCount > 0) {
          message += ` ${missingCount} missing.`;
        }
      } else if (missingCount > 0) {
        message = "Selected assets were already removed.";
      }
      const updatedAt = removedCount > 0 ? new Date().toISOString() : null;
      setActionStatus("success");
      setActionMessage(message);
      setSelectedIds(new Set());
      const removedSet = new Set(response.removed);
      setItems((prev) => prev.filter((asset) => !removedSet.has(asset.id)));
      setAlbum((prev) =>
        prev
          ? {
              ...prev,
              item_count: response.item_count,
              updated_at: updatedAt ?? prev.updated_at
            }
          : prev
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to remove items from album.";
      setActionStatus("error");
      setActionMessage(message);
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    } finally {
      setIsRemoving(false);
    }
  }, [albumId, refreshSession, selectedIds]);

  useEffect(() => {
    void loadAlbum();
  }, [loadAlbum]);

  useEffect(() => {
    setSelectedIds(new Set());
    setActionStatus("idle");
    setActionMessage(null);
  }, [albumId]);

  const hasItems = items.length > 0;
  const isLoading = status === "loading";
  const selectedCount = selectedIds.size;
  const isActionError = actionStatus === "error";
  const isActionSuccess = actionStatus === "success";

  return (
    <section className="page">
      <header className="page-header album-header">
        <div>
          <Link className="ghost back-link" to="/app/albums">
            Back to albums
          </Link>
          <p className="eyebrow">Owner albums</p>
          <h1>{album ? album.title : "Album"}</h1>
          <p className="subhead">
            {album ? `${formatItemCount(album.item_count)} · ${formatAlbumUpdated(album)}` : ""}
          </p>
        </div>
        <div className="album-actions">
          <div className="pill-group">
            <span className="pill">{formatItemCount(album?.item_count ?? 0)}</span>
            {album && <span className="pill">{formatAlbumUpdated(album)}</span>}
            <span className="pill">{selectedCount} selected</span>
          </div>
          <div className="selection-tools">
            <button className="ghost" onClick={handleSelectAll} disabled={!hasItems}>
              Select all
            </button>
            <button className="ghost" onClick={handleClearSelection} disabled={selectedCount === 0}>
              Clear
            </button>
            <button
              className="primary"
              onClick={handleRemoveSelected}
              disabled={selectedCount === 0 || isRemoving}
            >
              Remove selected
            </button>
          </div>
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
      {error && (
        <div className="status error" role="alert">
          {error}
        </div>
      )}
      {isLoading && !hasItems && (
        <div className="status" role="status">
          Loading album...
        </div>
      )}
      {!isLoading && !hasItems && !error && (
        <div className="status" role="status">
          This album is empty. Add assets from the timeline to start curating.
        </div>
      )}
      {hasItems && (
        <div className="grid album-grid stagger">
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
                className={`media-card album-media-card${isSelected ? " is-selected" : ""}`}
                style={{ "--delay": `${index * 0.03}s` } as CSSProperties}
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
    </section>
  );
}
