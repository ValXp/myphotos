import type { ChangeEvent, CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useLivePhotoHover } from "../hooks/useLivePhotoHover";
import { ViewerShell } from "./ViewerShell";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const PAGE_SIZE = 60;
const THUMB_PROFILE = "thumb_md";
const VIEWER_PROFILE = "thumb_lg";

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

type ScanStatus = {
  status: string;
  job_id: string | null;
  roots?: string[];
  stats?: {
    scanned: number;
    supported: number;
    created: number;
    updated: number;
    unchanged: number;
    errors: string[];
  } | null;
  started_at?: string | null;
  finished_at?: string | null;
  backoff_until?: string | null;
  error?: unknown;
};

type OverviewPayload = {
  scan: ScanStatus;
  assets: {
    count: number;
  };
  jobs: {
    metadata: Record<string, number>;
    thumb: Record<string, number>;
    transcode: Record<string, number>;
  };
  active_jobs: number;
};

type AlbumItemsResponse = {
  added: string[];
  skipped: string[];
  item_count: number;
};

type FilterDraft = {
  startDate: string;
  endDate: string;
  minLat: string;
  minLon: string;
  maxLat: string;
  maxLon: string;
};

type ActiveFilters = {
  start?: string;
  end?: string;
  minLat?: number;
  minLon?: number;
  maxLat?: number;
  maxLon?: number;
};

const FILTER_KEYS = [
  "startDate",
  "endDate",
  "minLat",
  "minLon",
  "maxLat",
  "maxLon"
] as const;

const EMPTY_FILTER_DRAFT: FilterDraft = {
  startDate: "",
  endDate: "",
  minLat: "",
  minLon: "",
  maxLat: "",
  maxLon: ""
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

function viewerPhotoUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/thumb?profile=${VIEWER_PROFILE}`);
}

function originalUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/original`);
}

function streamUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/stream/master.m3u8`);
}

function liveVideoUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/live`);
}

function buildAssetParams(cursor: string | null, filters: ActiveFilters): URLSearchParams {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) {
    params.set("cursor", cursor);
  }
  if (filters.start) {
    params.set("start", filters.start);
  }
  if (filters.end) {
    params.set("end", filters.end);
  }
  if (filters.minLat !== undefined) {
    params.set("min_lat", String(filters.minLat));
  }
  if (filters.minLon !== undefined) {
    params.set("min_lon", String(filters.minLon));
  }
  if (filters.maxLat !== undefined) {
    params.set("max_lat", String(filters.maxLat));
  }
  if (filters.maxLon !== undefined) {
    params.set("max_lon", String(filters.maxLon));
  }
  return params;
}

function parseDateInput(value: string, endOfDay: boolean): string | null {
  if (!value) {
    return null;
  }
  const parts = value.split("-");
  if (parts.length !== 3) {
    return null;
  }
  const year = Number(parts[0]);
  const month = Number(parts[1]);
  const day = Number(parts[2]);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return null;
  }
  const hours = endOfDay ? 23 : 0;
  const minutes = endOfDay ? 59 : 0;
  const seconds = endOfDay ? 59 : 0;
  const ms = endOfDay ? 999 : 0;
  const parsed = new Date(Date.UTC(year, month - 1, day, hours, minutes, seconds, ms));
  if (
    Number.isNaN(parsed.getTime()) ||
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return null;
  }
  return parsed.toISOString();
}

function parseNumberInput(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed) || !Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function hasFilterInput(filters: FilterDraft): boolean {
  return FILTER_KEYS.some((key) => filters[key].trim() !== "");
}

function sameFilterDraft(a: FilterDraft, b: FilterDraft): boolean {
  return FILTER_KEYS.every((key) => a[key] === b[key]);
}

function resolveFilters(draft: FilterDraft): { filters: ActiveFilters; error: string | null } {
  const errors: string[] = [];
  const start = parseDateInput(draft.startDate, false);
  const end = parseDateInput(draft.endDate, true);
  if (draft.startDate && !start) {
    errors.push("Start date is invalid.");
  }
  if (draft.endDate && !end) {
    errors.push("End date is invalid.");
  }
  if (start && end && new Date(start).getTime() > new Date(end).getTime()) {
    errors.push("Start date must be on or before end date.");
  }

  const bboxInputs = [draft.minLat, draft.minLon, draft.maxLat, draft.maxLon].map((value) =>
    value.trim()
  );
  const hasAnyBbox = bboxInputs.some(Boolean);
  let minLat: number | null = null;
  let minLon: number | null = null;
  let maxLat: number | null = null;
  let maxLon: number | null = null;
  if (hasAnyBbox) {
    if (bboxInputs.some((value) => value === "")) {
      errors.push("Enter all four bounds for location filtering.");
    } else {
      minLat = parseNumberInput(draft.minLat);
      minLon = parseNumberInput(draft.minLon);
      maxLat = parseNumberInput(draft.maxLat);
      maxLon = parseNumberInput(draft.maxLon);
      if (minLat === null || minLon === null || maxLat === null || maxLon === null) {
        errors.push("Location bounds must be valid numbers.");
      } else {
        if (minLat < -90 || maxLat > 90) {
          errors.push("Latitude bounds must be between -90 and 90.");
        }
        if (minLon < -180 || maxLon > 180) {
          errors.push("Longitude bounds must be between -180 and 180.");
        }
        if (minLat > maxLat || minLon > maxLon) {
          errors.push("Location bounds must be ordered from min to max.");
        }
      }
    }
  }

  if (errors.length > 0) {
    return { filters: {}, error: errors.join(" ") };
  }

  const filters: ActiveFilters = {};
  if (start) {
    filters.start = start;
  }
  if (end) {
    filters.end = end;
  }
  if (hasAnyBbox) {
    filters.minLat = minLat ?? undefined;
    filters.minLon = minLon ?? undefined;
    filters.maxLat = maxLat ?? undefined;
    filters.maxLon = maxLon ?? undefined;
  }
  return { filters, error: null };
}

function hasActiveFilters(filters: ActiveFilters): boolean {
  return (
    !!filters.start ||
    !!filters.end ||
    filters.minLat !== undefined ||
    filters.minLon !== undefined ||
    filters.maxLat !== undefined ||
    filters.maxLon !== undefined
  );
}

function buildEmptyFilterDraft(): FilterDraft {
  return { ...EMPTY_FILTER_DRAFT };
}

async function fetchAssets(cursor: string | null, filters: ActiveFilters): Promise<AssetsResponse> {
  const params = buildAssetParams(cursor, filters);
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
  const [filterDraft, setFilterDraft] = useState<FilterDraft>(() => buildEmptyFilterDraft());
  const [appliedFilterDraft, setAppliedFilterDraft] = useState<FilterDraft>(() =>
    buildEmptyFilterDraft()
  );
  const [activeFilters, setActiveFilters] = useState<ActiveFilters>({});
  const [filterError, setFilterError] = useState<string | null>(null);
  const [scanPath, setScanPath] = useState<string>("iphone_17_val_sample_videos");
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const inFlightRef = useRef(false);
  const { registerVideoRef, handleMouseEnter, handleMouseLeave } = useLivePhotoHover();
  const [searchParams, setSearchParams] = useSearchParams();

  const viewerOpen = searchParams.get("viewer") === "1";

  const loadAssets = useCallback(
    async (cursor: string | null, mode: "initial" | "more", filters: ActiveFilters) => {
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
        const data = await fetchAssets(cursor, filters);
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

  const fetchOverview = useCallback(async () => {
    try {
      const data = await requestJson<OverviewPayload>("/admin/index/overview", {
        method: "GET"
      });
      setOverview(data);
      setScanStatus(data.scan);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    }
  }, [refreshSession]);

  useEffect(() => {
    void fetchOverview();
    const interval = window.setInterval(() => {
      void fetchOverview();
    }, 2000);
    return () => window.clearInterval(interval);
  }, [fetchOverview]);

  const runScan = useCallback(async () => {
    setIsScanning(true);
    setScanMessage(null);
    try {
      const params = new URLSearchParams();
      const trimmed = scanPath.trim();
      if (trimmed) {
        // The API accepts relative paths under ORIGINALS_DIR as well.
        params.append("path", trimmed);
      }
      const query = params.toString();
      const data = await requestJson<ScanStatus>(
        `/admin/index/scan${query ? `?${query}` : ""}`,
        { method: "POST" }
      );
      setScanStatus(data);
      setScanMessage("Scan started.");
      void fetchOverview();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to start scan.";
      setScanMessage(message);
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    } finally {
      setIsScanning(false);
    }
  }, [fetchOverview, refreshSession, scanPath]);

  const handleRefresh = useCallback(() => {
    void loadAssets(null, "initial", activeFilters);
    void loadAlbums();
  }, [activeFilters, loadAssets, loadAlbums]);

  const handleLoadMore = useCallback(() => {
    if (!nextCursor) {
      return;
    }
    void loadAssets(nextCursor, "more", activeFilters);
  }, [activeFilters, loadAssets, nextCursor]);

  const handleFilterChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    const key = name as keyof FilterDraft;
    setFilterDraft((prev) => ({ ...prev, [key]: value }));
    setFilterError(null);
  }, []);

  const handleApplyFilters = useCallback(() => {
    const resolved = resolveFilters(filterDraft);
    if (resolved.error) {
      setFilterError(resolved.error);
      return;
    }
    setFilterError(null);
    setAppliedFilterDraft(filterDraft);
    setActiveFilters(resolved.filters);
  }, [filterDraft]);

  const handleClearFilters = useCallback(() => {
    const cleared = buildEmptyFilterDraft();
    setFilterDraft(cleared);
    setAppliedFilterDraft(cleared);
    setFilterError(null);
    setActiveFilters({});
  }, []);

  const openViewer = useCallback(
    (assetId: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("asset", assetId);
        next.set("viewer", "1");
        return next;
      });
    },
    [setSearchParams]
  );

  const closeViewer = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("viewer");
      next.delete("asset");
      return next;
    });
  }, [setSearchParams]);

  useEffect(() => {
    if (!viewerOpen) {
      return;
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeViewer();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [closeViewer, viewerOpen]);

  useEffect(() => {
    void loadAssets(null, "initial", activeFilters);
  }, [activeFilters, loadAssets]);

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
  const hasFilterChanges = !sameFilterDraft(filterDraft, appliedFilterDraft);
  const hasDraftFilters = hasFilterInput(filterDraft);
  const hasAppliedFilters = hasActiveFilters(activeFilters);
  const canApplyFilters = hasFilterChanges && !isLoading && !isLoadingMore && !isAdding;
  const canClearFilters = (hasDraftFilters || hasAppliedFilters) && !isLoading && !isAdding;
  const hasAlbums = albums.length > 0;
  const isAlbumLoading = albumStatus === "loading";
  const isActionError = actionStatus === "error";
  const isActionSuccess = actionStatus === "success";
  const filterPills: string[] = [];
  if (activeFilters.start || activeFilters.end) {
    filterPills.push("Date range");
  }
  if (activeFilters.minLat !== undefined) {
    filterPills.push("Location bounds");
  }

  return (
    <section className="page">
      <header className="page-header timeline-header">
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
            {filterPills.map((label) => (
              <span className="pill" key={label}>
                {label}
              </span>
            ))}
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

          <div className="scan-controls" role="group" aria-label="Index scan controls">
            <input
              className="text-input"
              value={scanPath}
              onChange={(event) => setScanPath(event.target.value)}
              placeholder="Folder under originals (blank = all)"
              aria-label="Scan folder"
            />
            <button className="ghost" onClick={() => void runScan()} disabled={isScanning}>
              {isScanning ? "Scanning..." : "Scan"}
            </button>
          </div>

          <button className="ghost" onClick={handleRefresh} disabled={isLoading || isAdding}>
            Refresh
          </button>
        </div>
        <div className="timeline-filters" role="group" aria-label="Timeline filters">
          <div className="filter-section">
            <p className="filter-title">Date range</p>
            <div className="filter-row">
              <label className="field" htmlFor="filter-start-date">
                <span>Start date</span>
                <input
                  id="filter-start-date"
                  name="startDate"
                  className="text-input"
                  type="date"
                  value={filterDraft.startDate}
                  onChange={handleFilterChange}
                />
              </label>
              <label className="field" htmlFor="filter-end-date">
                <span>End date</span>
                <input
                  id="filter-end-date"
                  name="endDate"
                  className="text-input"
                  type="date"
                  value={filterDraft.endDate}
                  onChange={handleFilterChange}
                />
              </label>
            </div>
          </div>
          <div className="filter-section">
            <p className="filter-title">Location bounds</p>
            <div className="filter-row">
              <label className="field" htmlFor="filter-min-lat">
                <span>Min lat</span>
                <input
                  id="filter-min-lat"
                  name="minLat"
                  className="text-input"
                  type="number"
                  step="0.0001"
                  value={filterDraft.minLat}
                  onChange={handleFilterChange}
                  placeholder="-90 to 90"
                />
              </label>
              <label className="field" htmlFor="filter-min-lon">
                <span>Min lon</span>
                <input
                  id="filter-min-lon"
                  name="minLon"
                  className="text-input"
                  type="number"
                  step="0.0001"
                  value={filterDraft.minLon}
                  onChange={handleFilterChange}
                  placeholder="-180 to 180"
                />
              </label>
              <label className="field" htmlFor="filter-max-lat">
                <span>Max lat</span>
                <input
                  id="filter-max-lat"
                  name="maxLat"
                  className="text-input"
                  type="number"
                  step="0.0001"
                  value={filterDraft.maxLat}
                  onChange={handleFilterChange}
                  placeholder="-90 to 90"
                />
              </label>
              <label className="field" htmlFor="filter-max-lon">
                <span>Max lon</span>
                <input
                  id="filter-max-lon"
                  name="maxLon"
                  className="text-input"
                  type="number"
                  step="0.0001"
                  value={filterDraft.maxLon}
                  onChange={handleFilterChange}
                  placeholder="-180 to 180"
                />
              </label>
            </div>
          </div>
          <div className="timeline-filter-actions">
            <button className="ghost" onClick={handleApplyFilters} disabled={!canApplyFilters}>
              Apply filters
            </button>
            <button className="ghost" onClick={handleClearFilters} disabled={!canClearFilters}>
              Clear filters
            </button>
            {hasAppliedFilters && <span className="hint">Filters applied to timeline results.</span>}
          </div>
        </div>
      </header>

      {viewerOpen && (
        <div className="viewer-overlay" onClick={closeViewer} role="dialog" aria-modal="true">
          <div className="viewer-overlay-panel" onClick={(event) => event.stopPropagation()}>
            <button className="viewer-overlay-close ghost" onClick={closeViewer}>
              Close
            </button>
            <ViewerShell
              contextLabel="Owner timeline"
              emptyMessage="No assets loaded."
              emptySubhead="Pick an asset from the timeline."
              items={items}
              status={
                status === "loading" || status === "loading-more"
                  ? "loading"
                  : status === "ready"
                    ? "ready"
                    : status === "error"
                      ? "error"
                      : "idle"
              }
              error={error}
              nextCursor={nextCursor}
              previewUrl={thumbnailUrl}
              photoUrl={viewerPhotoUrl}
              streamUrl={streamUrl}
              showFooterNav={false}
            />
          </div>
        </div>
      )}

      {(scanMessage || overview) && (
        <div className="status" role="status">
          {scanMessage && (
            <span>
              {scanMessage}
              {scanStatus?.job_id ? ` (job ${scanStatus.job_id})` : ""}
            </span>
          )}
          {overview?.scan?.status && (
            <span>
              {scanMessage ? " · " : ""}
              Scan: {overview.scan.status}
              {overview.scan.stats
                ? ` (created ${overview.scan.stats.created}, updated ${overview.scan.stats.updated})`
                : ""}
              {overview.scan.stats?.errors?.length
                ? ` · Scan errors: ${overview.scan.stats.errors.slice(0, 1).join("")}`
                : ""}
              {` · Assets: ${overview.assets.count}`}
              {` · Jobs active: ${overview.active_jobs}`}
            </span>
          )}
        </div>
      )}
      {filterError && (
        <div className="status error" role="alert">
          {filterError}
        </div>
      )}
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
                  role="button"
                  tabIndex={0}
                  onClick={() => openViewer(asset.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openViewer(asset.id);
                    }
                  }}
                  onMouseEnter={isLivePhoto ? () => handleMouseEnter(asset.id) : undefined}
                  onMouseLeave={isLivePhoto ? () => handleMouseLeave(asset.id) : undefined}
                  aria-label={`Open ${typeLabel.toLowerCase()} viewer`}
                >
                  <label className="media-select" onClick={(event) => event.stopPropagation()}>
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
