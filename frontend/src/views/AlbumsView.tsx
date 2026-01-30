import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
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

type AlbumsResponse = {
  items: AlbumSummary[];
};

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

function formatDate(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return dateFormatter.format(parsed);
}

function formatItemCount(count: number): string {
  return `${count} item${count === 1 ? "" : "s"}`;
}

function formatAlbumMeta(album: AlbumSummary): string {
  const updatedLabel = formatDate(album.updated_at ?? album.created_at);
  if (!updatedLabel) {
    return formatItemCount(album.item_count);
  }
  return `${formatItemCount(album.item_count)} · Updated ${updatedLabel}`;
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

export function AlbumsView() {
  const { refreshSession } = useAuth();
  const [albums, setAlbums] = useState<AlbumSummary[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const loadAlbums = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const data = await requestJson<AlbumsResponse>("/albums", { method: "GET" });
      setAlbums(data.items);
      setStatus("ready");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load albums.";
      setError(message);
      setStatus("error");
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    }
  }, [refreshSession]);

  useEffect(() => {
    void loadAlbums();
  }, [loadAlbums]);

  const handleRefresh = useCallback(() => {
    void loadAlbums();
  }, [loadAlbums]);

  const handleCreate = useCallback(async () => {
    const rawTitle = window.prompt("Album title");
    if (!rawTitle) {
      return;
    }
    const title = rawTitle.trim();
    if (!title) {
      return;
    }
    setIsCreating(true);
    setError(null);
    try {
      await requestJson<AlbumSummary>("/albums", {
        method: "POST",
        body: JSON.stringify({ title })
      });
      await loadAlbums();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create album.";
      setError(message);
      if (err instanceof ApiError && err.status === 401) {
        await refreshSession();
      }
    } finally {
      setIsCreating(false);
    }
  }, [loadAlbums, refreshSession]);

  const hasAlbums = albums.length > 0;
  const isLoading = status === "loading";

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Owner albums</p>
          <h1>Albums</h1>
          <p className="subhead">Create, sort, and share your curated sets.</p>
        </div>
        <div className="album-actions">
          <div className="pill-group">
            <span className="pill">{albums.length} albums</span>
          </div>
          <button className="ghost" onClick={handleRefresh} disabled={isLoading || isCreating}>
            Refresh
          </button>
          <button className="primary" onClick={handleCreate} disabled={isCreating}>
            New album
          </button>
        </div>
      </header>
      {error && (
        <div className="status error" role="alert">
          {error}
        </div>
      )}
      {isLoading && !hasAlbums && (
        <div className="status" role="status">
          Loading albums...
        </div>
      )}
      {!isLoading && !hasAlbums && !error && (
        <div className="status" role="status">
          No albums yet. Create one to start curating a collection.
        </div>
      )}
      {hasAlbums && (
        <div className="grid stagger">
          {albums.map((album, index) => (
            <Link
              key={album.id}
              to={`/app/albums/${album.id}`}
              className="album-card"
              style={{ "--delay": `${index * 0.08}s` } as CSSProperties}
            >
              <div className="album-cover" aria-hidden="true">
                <span className="album-count">{formatItemCount(album.item_count)}</span>
              </div>
              <div className="media-meta">
                <h3>{album.title}</h3>
                <p>{formatAlbumMeta(album)}</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
