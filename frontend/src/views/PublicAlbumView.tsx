import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

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

type PublicAlbum = {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
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
    headers
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

function formatToken(token: string | undefined): string {
  if (!token) {
    return "unknown";
  }
  if (token.length <= 10) {
    return token;
  }
  return `${token.slice(0, 6)}...${token.slice(-4)}`;
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

function formatAlbumUpdated(album: PublicAlbum): string {
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

function thumbnailUrl(token: string, assetId: string): string {
  const safeToken = encodeURIComponent(token);
  const safeId = encodeURIComponent(assetId);
  return buildApiUrl(
    `/public/shares/${safeToken}/assets/${safeId}/thumb?profile=${THUMB_PROFILE}`
  );
}

export function PublicAlbumView() {
  const { token } = useParams();
  const tokenLabel = useMemo(() => formatToken(token), [token]);
  const [album, setAlbum] = useState<PublicAlbum | null>(null);
  const [items, setItems] = useState<AssetSummary[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const loadShare = useCallback(async () => {
    if (!token) {
      setStatus("error");
      setError("Share link missing.");
      return;
    }
    setStatus("loading");
    setError(null);
    setAlbum(null);
    setItems([]);
    try {
      const safeToken = encodeURIComponent(token);
      const [albumData, assetsData] = await Promise.all([
        requestJson<PublicAlbum>(`/public/shares/${safeToken}/album`, { method: "GET" }),
        requestJson<AlbumAssetsResponse>(`/public/shares/${safeToken}/assets`, { method: "GET" })
      ]);
      setAlbum(albumData);
      setItems(assetsData.items);
      setStatus("ready");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load shared album.";
      setError(message);
      setStatus("error");
    }
  }, [token]);

  useEffect(() => {
    void loadShare();
  }, [loadShare]);

  const hasItems = items.length > 0;
  const isLoading = status === "loading";

  return (
    <section className="public-page">
      <header className="public-hero">
        <div className="public-hero-copy">
          <p className="eyebrow">Public share</p>
          <h1>{album ? album.title : "Welcome to a public share"}</h1>
          <p className="subhead">
            Browse the moments shared with this link, curated straight from the owner
            library.
          </p>
          <div className="pill-group">
            <span className="pill">{formatItemCount(items.length)}</span>
            {album && <span className="pill">{formatAlbumUpdated(album)}</span>}
          </div>
        </div>
        <div className="public-token-card" aria-live="polite">
          <p className="eyebrow">Share token</p>
          <p className="public-token-value">{tokenLabel}</p>
          <p className="hint">
            {status === "ready"
              ? "Save this link to revisit the album anytime."
              : "Share links keep this album scoped and private."}
          </p>
        </div>
      </header>
      {error && (
        <div className="status error" role="alert">
          {error}
        </div>
      )}
      {isLoading && !hasItems && (
        <div className="status" role="status">
          Loading shared album...
        </div>
      )}
      {!isLoading && !hasItems && !error && (
        <div className="status" role="status">
          This shared album does not have any items yet.
        </div>
      )}
      {hasItems && (
        <div className="grid album-grid stagger public-grid">
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
                className="media-card album-media-card"
                style={{ "--delay": `${index * 0.03}s` } as CSSProperties}
              >
                <div className="media-thumb">
                  <img
                    src={token ? thumbnailUrl(token, asset.id) : undefined}
                    alt={thumbAlt}
                    loading="lazy"
                  />
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
