import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ViewerShell, ViewerAsset, ViewerStatus } from "./ViewerShell";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type PublicAssetsResponse = {
  items: ViewerAsset[];
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

function publicThumbnailUrl(token: string, assetId: string): string {
  const safeToken = encodeURIComponent(token);
  const safeId = encodeURIComponent(assetId);
  return buildApiUrl(`/public/shares/${safeToken}/assets/${safeId}/thumb`);
}

function publicStreamUrl(token: string, assetId: string): string {
  const safeToken = encodeURIComponent(token);
  const safeId = encodeURIComponent(assetId);
  return buildApiUrl(`/public/shares/${safeToken}/assets/${safeId}/stream/master.m3u8`);
}

function publicLiveUrl(token: string, assetId: string): string {
  const safeToken = encodeURIComponent(token);
  const safeId = encodeURIComponent(assetId);
  return buildApiUrl(`/public/shares/${safeToken}/assets/${safeId}/live`);
}

export function PublicViewerView() {
  const { token } = useParams();
  const [items, setItems] = useState<ViewerAsset[]>([]);
  const [status, setStatus] = useState<ViewerStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const loadAssets = useCallback(async () => {
    if (!token) {
      setStatus("error");
      setError("Share link missing.");
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const safeToken = encodeURIComponent(token);
      const data = await requestJson<PublicAssetsResponse>(
        `/public/shares/${safeToken}/assets`,
        { method: "GET" }
      );
      setItems(data.items);
      setStatus("ready");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load shared assets.";
      setError(message);
      setStatus("error");
    }
  }, [token]);

  useEffect(() => {
    void loadAssets();
  }, [loadAssets]);

  const thumbBuilder = useCallback(
    (assetId: string) => (token ? publicThumbnailUrl(token, assetId) : ""),
    [token]
  );

  const streamBuilder = useCallback(
    (assetId: string) => (token ? publicStreamUrl(token, assetId) : ""),
    [token]
  );

  const liveBuilder = useCallback(
    (assetId: string) => (token ? publicLiveUrl(token, assetId) : ""),
    [token]
  );

  const backLink = token
    ? { to: `/share/${encodeURIComponent(token)}`, label: "Back to album" }
    : undefined;

  return (
    <ViewerShell
      contextLabel="Shared album viewer"
      emptyMessage="This shared album does not have any items yet."
      emptySubhead="Pick an asset from the shared album."
      loadingMessage="Loading shared viewer..."
      items={items}
      status={status}
      error={error}
      previewUrl={thumbBuilder}
      streamUrl={streamBuilder}
      liveUrl={liveBuilder}
      backLink={backLink}
    />
  );
}
