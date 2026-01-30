import type { CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";

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

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
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

async function fetchAssets(cursor: string | null): Promise<AssetsResponse> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) {
    params.set("cursor", cursor);
  }
  const response = await fetch(buildApiUrl(`/assets?${params.toString()}`), {
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
  return (await response.json()) as AssetsResponse;
}

export function TimelineView() {
  const { refreshSession } = useAuth();
  const [items, setItems] = useState<AssetSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "loading-more" | "error">(
    "idle"
  );
  const [error, setError] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const inFlightRef = useRef(false);

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

  const handleRefresh = useCallback(() => {
    void loadAssets(null, "initial");
  }, [loadAssets]);

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
          </div>
          <button className="ghost" onClick={handleRefresh} disabled={isLoading}>
            Refresh
          </button>
        </div>
      </header>
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

            return (
              <article
                key={asset.id}
                className="media-card timeline-card"
                style={{ "--delay": `${index * 0.04}s` } as CSSProperties}
              >
                <div className="media-thumb">
                  <img src={thumbnailUrl(asset.id)} alt={thumbAlt} loading="lazy" />
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
