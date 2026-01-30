import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

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

type ZipStatus = "idle" | "queued" | "running" | "done" | "failed";

type ZipStatusResponse = {
  status: ZipStatus;
  album_id: string;
  job_id: string | null;
  asset_count: number | null;
  zip_bytes: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  invalidated_at: string | null;
  download_url: string | null;
  error: string | null;
};

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

function resolveApiUrl(path: string): string {
  if (!path) {
    return path;
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return buildApiUrl(path);
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

function formatBytes(bytes: number | null): string | null {
  if (!bytes || bytes <= 0) {
    return null;
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const decimals = size < 10 && unitIndex > 0 ? 1 : 0;
  return `${size.toFixed(decimals)} ${units[unitIndex]}`;
}

function formatTimestamp(value: string | null): string | null {
  const date = parseDate(value);
  if (!date) {
    return null;
  }
  return `${dateFormatter.format(date)} at ${timeFormatter.format(date)}`;
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

function formatZipStatusLabel(status: ZipStatus | null | undefined): string {
  if (!status) {
    return "Checking download status...";
  }
  if (status === "idle") {
    return "No ZIP ready yet.";
  }
  if (status === "queued") {
    return "ZIP queued for preparation.";
  }
  if (status === "running") {
    return "Preparing the ZIP bundle.";
  }
  if (status === "done") {
    return "ZIP ready to download.";
  }
  if (status === "failed") {
    return "ZIP failed to generate.";
  }
  return "Checking download status...";
}

function thumbnailUrl(token: string, assetId: string): string {
  const safeToken = encodeURIComponent(token);
  const safeId = encodeURIComponent(assetId);
  return buildApiUrl(
    `/public/shares/${safeToken}/assets/${safeId}/thumb?profile=${THUMB_PROFILE}`
  );
}

function originalDownloadUrl(token: string, assetId: string): string {
  const safeToken = encodeURIComponent(token);
  const safeId = encodeURIComponent(assetId);
  return buildApiUrl(`/public/shares/${safeToken}/assets/${safeId}/original`);
}

function viewerLink(token: string, assetId: string): string {
  const safeToken = encodeURIComponent(token);
  const safeId = encodeURIComponent(assetId);
  return `/share/${safeToken}/viewer?asset=${safeId}`;
}

export function PublicAlbumView() {
  const { token } = useParams();
  const tokenLabel = useMemo(() => formatToken(token), [token]);
  const [album, setAlbum] = useState<PublicAlbum | null>(null);
  const [items, setItems] = useState<AssetSummary[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [zipInfo, setZipInfo] = useState<ZipStatusResponse | null>(null);
  const [zipAction, setZipAction] = useState<"idle" | "checking" | "starting">("idle");
  const [zipError, setZipError] = useState<string | null>(null);

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

  const loadZipStatus = useCallback(
    async (silent = false) => {
      if (!token) {
        if (!silent) {
          setZipError("Share link missing.");
        }
        return;
      }
      if (!silent) {
        setZipAction("checking");
        setZipError(null);
      }
      try {
        const safeToken = encodeURIComponent(token);
        const zipData = await requestJson<ZipStatusResponse>(
          `/public/shares/${safeToken}/zip`,
          { method: "GET" }
        );
        setZipInfo(zipData);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unable to load ZIP status.";
        if (!silent) {
          setZipError(message);
        }
      } finally {
        if (!silent) {
          setZipAction("idle");
        }
      }
    },
    [token]
  );

  const handleZipStart = useCallback(async () => {
    if (!token) {
      setZipError("Share link missing.");
      return;
    }
    setZipAction("starting");
    setZipError(null);
    try {
      const safeToken = encodeURIComponent(token);
      const zipData = await requestJson<ZipStatusResponse>(
        `/public/shares/${safeToken}/zip`,
        { method: "POST" }
      );
      setZipInfo(zipData);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to prepare ZIP download.";
      setZipError(message);
    } finally {
      setZipAction("idle");
    }
  }, [token]);

  useEffect(() => {
    void loadShare();
  }, [loadShare]);

  useEffect(() => {
    setZipInfo(null);
    setZipError(null);
    setZipAction("idle");
  }, [token]);

  useEffect(() => {
    void loadZipStatus();
  }, [loadZipStatus]);

  useEffect(() => {
    if (!zipInfo || (zipInfo.status !== "queued" && zipInfo.status !== "running")) {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadZipStatus(true);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [zipInfo, loadZipStatus]);

  const hasItems = items.length > 0;
  const isLoading = status === "loading";
  const zipInProgress = zipInfo?.status === "queued" || zipInfo?.status === "running";
  const zipDownloadUrl = zipInfo?.download_url ? resolveApiUrl(zipInfo.download_url) : null;
  const zipStatusMessage = zipError
    ? zipError
    : zipAction === "starting"
      ? "Starting ZIP job..."
      : zipAction === "checking" && !zipInfo
        ? "Checking download status..."
        : formatZipStatusLabel(zipInfo?.status);
  const zipStatusTone = zipError || zipInfo?.status === "failed" ? "error" : zipInfo?.status === "done" ? "success" : "";
  const zipFailureDetail =
    !zipError && zipInfo?.status === "failed" && zipInfo.error
      ? `Error: ${zipInfo.error}`
      : null;
  const zipMetaParts: string[] = [];
  if (zipInfo?.asset_count) {
    zipMetaParts.push(formatItemCount(zipInfo.asset_count));
  }
  const zipSize = formatBytes(zipInfo?.zip_bytes ?? null);
  if (zipSize) {
    zipMetaParts.push(zipSize);
  }
  const finishedLabel = formatTimestamp(zipInfo?.finished_at ?? zipInfo?.created_at ?? null);
  if (finishedLabel && zipInfo?.status === "done") {
    zipMetaParts.push(`Ready ${finishedLabel}`);
  }
  const startedLabel = formatTimestamp(zipInfo?.started_at ?? null);
  if (startedLabel && zipInfo && zipInfo.status !== "done") {
    zipMetaParts.push(`Started ${startedLabel}`);
  }
  const zipPrimaryLabel = zipAction === "starting"
    ? "Starting ZIP..."
    : zipInProgress
      ? "Preparing ZIP..."
      : zipInfo?.status === "failed"
        ? "Retry ZIP"
        : "Prepare ZIP";
  const isZipBusy = zipAction !== "idle";

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
      <div className="public-panels">
        <div className="public-panel accent public-download">
          <p className="eyebrow">Download</p>
          <h2>Take the originals with you</h2>
          <p className="subhead">
            Generate a ZIP of the original files. Large albums can take a moment to
            prepare.
          </p>
          <div
            className={`status${zipStatusTone ? ` ${zipStatusTone}` : ""}`}
            role={zipStatusTone === "error" ? "alert" : "status"}
          >
            {zipStatusMessage}
          </div>
          {zipFailureDetail && <p className="hint">{zipFailureDetail}</p>}
          {zipMetaParts.length > 0 && (
            <div className="pill-group">
              {zipMetaParts.map((part) => (
                <span className="pill" key={part}>
                  {part}
                </span>
              ))}
            </div>
          )}
          <div className="zip-actions">
            {zipDownloadUrl && zipInfo?.status === "done" ? (
              <a className="primary" href={zipDownloadUrl} rel="noreferrer">
                Download ZIP
              </a>
            ) : (
              <button
                className="primary"
                onClick={handleZipStart}
                disabled={!token || isZipBusy || zipInProgress}
              >
                {zipPrimaryLabel}
              </button>
            )}
            <button
              className="ghost"
              onClick={() => void loadZipStatus()}
              disabled={!token || isZipBusy}
            >
              Check status
            </button>
          </div>
          <p className="hint">ZIPs update automatically when the album changes.</p>
        </div>
      </div>
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
            const downloadUrl = token ? originalDownloadUrl(token, asset.id) : "";

            return (
              <article
                key={asset.id}
                className="media-card album-media-card"
                style={{ "--delay": `${index * 0.03}s` } as CSSProperties}
              >
                <Link
                  className="media-thumb"
                  to={token ? viewerLink(token, asset.id) : "#"}
                  aria-label={`Open ${typeLabel} in viewer`}
                >
                  <img
                    src={token ? thumbnailUrl(token, asset.id) : undefined}
                    alt={thumbAlt}
                    loading="lazy"
                  />
                  <span className="media-badge">{typeLabel}</span>
                  {durationLabel && <span className="media-duration">{durationLabel}</span>}
                </Link>
                <div className="media-meta">
                  <h3>{dateLabel}</h3>
                  {metaParts.length > 0 && <p>{metaParts.join(" · ")}</p>}
                </div>
                <div className="media-actions">
                  <a
                    className="ghost"
                    href={downloadUrl}
                    download
                    aria-label={`Download original ${typeLabel} from ${dateLabel}`}
                  >
                    Download original
                  </a>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
