import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { ViewerShell, ViewerAsset, ViewerStatus } from "./ViewerShell";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const PAGE_SIZE = 200;

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type AssetsResponse = {
  items: ViewerAsset[];
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

function previewUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/thumb`);
}

function originalUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/original`);
}

function streamUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/stream/master.m3u8`);
}

function liveUrl(assetId: string): string {
  return buildApiUrl(`/assets/${assetId}/live`);
}

async function fetchAssets(): Promise<AssetsResponse> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  return requestJson<AssetsResponse>(`/assets?${params.toString()}`, { method: "GET" });
}

export function ViewerView() {
  const { refreshSession } = useAuth();
  const [items, setItems] = useState<ViewerAsset[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [status, setStatus] = useState<ViewerStatus>("idle");
  const [error, setError] = useState<string | null>(null);

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

  return (
    <ViewerShell
      contextLabel="Owner viewer"
      emptyMessage="No assets yet. Add photos or videos to start viewing."
      emptySubhead="Pick an asset from the timeline."
      items={items}
      status={status}
      error={error}
      nextCursor={nextCursor}
      previewUrl={previewUrl}
      photoUrl={originalUrl}
      streamUrl={streamUrl}
      liveUrl={liveUrl}
      backLink={{ to: "/app/timeline", label: "Back to timeline" }}
    />
  );
}
