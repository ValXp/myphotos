import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as webauthn from "./auth/webauthn";

vi.mock("./auth/webauthn", () => {
  class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  }

  return {
    ApiError,
    fetchSessionStatus: vi.fn(),
    logout: vi.fn(),
    registerPasskey: vi.fn(),
    signInWithPasskey: vi.fn(),
    isPasskeySupported: vi.fn(() => true),
    isSecureContext: vi.fn(() => true)
  };
});

const mockedSessionStatus = vi.mocked(webauthn.fetchSessionStatus);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("App flows", () => {
  it("renders sign-in when unauthenticated", async () => {
    mockedSessionStatus.mockResolvedValue(false);

    render(
      <MemoryRouter initialEntries={["/app/timeline"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText(/unlock your library/i)).toBeInTheDocument();
  });

  it("renders public album routes without authentication", async () => {
    mockedSessionStatus.mockResolvedValue(false);

    const albumPayload = {
      id: "album-public-1",
      title: "Weekend share",
      created_at: "2026-01-12T08:00:00Z",
      updated_at: "2026-01-18T08:00:00Z"
    };

    const assetsPayload = {
      items: [
        {
          id: "asset-public-1",
          type: "photo",
          captured_at: "2026-01-20T16:30:00Z",
          created_at: "2026-01-20T16:30:00Z",
          duration_ms: null,
          width: 4032,
          height: 3024,
          live_photo_video_id: null
        }
      ]
    };

    const zipStatusPayload = {
      status: "idle",
      album_id: "album-public-1",
      job_id: null,
      asset_count: 1,
      zip_bytes: null,
      started_at: null,
      finished_at: null,
      created_at: null,
      invalidated_at: null,
      download_url: null,
      error: null
    };

    const fetchMock = vi.fn().mockImplementation((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/public/shares/demo-token/album")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => albumPayload
        });
      }
      if (url.includes("/public/shares/demo-token/assets")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => assetsPayload
        });
      }
      if (url.includes("/public/shares/demo-token/zip")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => zipStatusPayload
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({})
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/share/demo-token"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText(/public share/i)).toBeInTheDocument();
    expect(screen.getByText(/weekend share/i)).toBeInTheDocument();
    expect(screen.getByText(/demo-token/i)).toBeInTheDocument();
    expect(
      await screen.findByRole("img", { name: "Photo thumbnail from Jan 20, 2026" })
    ).toHaveAttribute("src", expect.stringContaining("/public/shares/demo-token/assets"));
    expect(
      await screen.findByRole("button", { name: /prepare zip/i })
    ).toBeInTheDocument();
    const downloadLink = await screen.findByRole("link", { name: /download original/i });
    expect(downloadLink).toHaveAttribute(
      "href",
      expect.stringContaining("/public/shares/demo-token/assets/asset-public-1/original")
    );
    expect(screen.queryByText(/unlock your library/i)).not.toBeInTheDocument();
  });

  it("renders public viewer video playback and live photo preview", async () => {
    mockedSessionStatus.mockResolvedValue(false);

    const assetsPayload = {
      items: [
        {
          id: "asset-public-video",
          type: "video",
          captured_at: "2026-01-20T16:30:00Z",
          created_at: "2026-01-20T16:30:00Z",
          duration_ms: 64000,
          width: 1920,
          height: 1080,
          live_photo_video_id: null
        },
        {
          id: "asset-public-live",
          type: "live_photo",
          captured_at: "2026-01-18T10:05:00Z",
          created_at: "2026-01-18T10:05:00Z",
          duration_ms: null,
          width: 3024,
          height: 4032,
          live_photo_video_id: "asset-live-video"
        }
      ]
    };

    const fetchMock = vi.fn().mockImplementation((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/public/shares/demo-token/assets")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => assetsPayload
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({})
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(
      <MemoryRouter initialEntries={["/share/demo-token/viewer?asset=asset-public-video"]}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByLabelText(/video playback from jan 20, 2026/i)
    ).toBeInTheDocument();
    expect(container.querySelector("video")).toBeInTheDocument();
    // video.js attaches sources dynamically; in tests we expose the intended URL.
    expect(
      container.querySelector("video")?.getAttribute("data-stream-src")
    ).toContain("/public/shares/demo-token/assets/asset-public-video/stream");

    cleanup();

    render(
      <MemoryRouter initialEntries={["/share/demo-token/viewer?asset=asset-public-live"]}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByRole("img", { name: /live photo preview from jan 18, 2026/i })
    ).toBeInTheDocument();
  });

  it("uses originals for owner photo viewer and keeps video posters as thumbnails", async () => {
    mockedSessionStatus.mockResolvedValue(true);

    const assetsPayload = {
      items: [
        {
          id: "asset-owner-photo",
          type: "photo",
          captured_at: "2026-01-22T16:30:00Z",
          created_at: "2026-01-22T16:30:00Z",
          duration_ms: null,
          width: 4032,
          height: 3024,
          live_photo_video_id: null
        },
        {
          id: "asset-owner-video",
          type: "video",
          captured_at: "2026-01-23T18:10:00Z",
          created_at: "2026-01-23T18:10:00Z",
          duration_ms: 64000,
          width: 1920,
          height: 1080,
          live_photo_video_id: null
        }
      ],
      next_cursor: null
    };

    const fetchMock = vi.fn().mockImplementation((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/assets?")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => assetsPayload
        });
      }
      if (url.includes("/albums")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => ({ items: [] })
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({})
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(
      <MemoryRouter initialEntries={["/app/timeline?viewer=1&asset=asset-owner-photo"]}>
        <App />
      </MemoryRouter>
    );

    const photoImg = await screen.findByRole("img", {
      name: /photo preview from jan 22, 2026/i
    });
    expect(photoImg).toHaveAttribute(
      "src",
      expect.stringContaining("/assets/asset-owner-photo/thumb?profile=thumb_lg")
    );
    expect(container.querySelector("video")).not.toBeInTheDocument();

    cleanup();

    render(
      <MemoryRouter initialEntries={["/app/timeline?viewer=1&asset=asset-owner-video"]}>
        <App />
      </MemoryRouter>
    );

    const video = await screen.findByLabelText(/video playback from jan 23, 2026/i);
    // In browsers the video src is attached by hls.js; in tests we expose the intended
    // stream URL via a data attribute.
    expect(video).toHaveAttribute(
      "data-stream-src",
      expect.stringContaining("/assets/asset-owner-video/stream")
    );
    expect(video).toHaveAttribute(
      "poster",
      expect.stringContaining("/assets/asset-owner-video/thumb")
    );
  });

  it("starts and completes public ZIP downloads", async () => {
    mockedSessionStatus.mockResolvedValue(false);

    const albumPayload = {
      id: "album-public-zip",
      title: "Holiday share",
      created_at: "2026-01-10T08:00:00Z",
      updated_at: "2026-01-12T08:00:00Z"
    };

    const assetsPayload = {
      items: []
    };

    const zipStatusIdle = {
      status: "idle",
      album_id: "album-public-zip",
      job_id: null,
      asset_count: null,
      zip_bytes: null,
      started_at: null,
      finished_at: null,
      created_at: null,
      invalidated_at: null,
      download_url: null,
      error: null
    };

    const zipStatusDone = {
      status: "done",
      album_id: "album-public-zip",
      job_id: "job-zip-1",
      asset_count: 14,
      zip_bytes: 2048,
      started_at: "2026-01-20T10:00:00Z",
      finished_at: "2026-01-20T10:01:00Z",
      created_at: "2026-01-20T10:01:00Z",
      invalidated_at: null,
      download_url: "/public/shares/demo-token/zip/download",
      error: null
    };

    const fetchMock = vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      const method =
        (init?.method ?? (typeof input === "string" ? "GET" : input.method)).toUpperCase();
      if (url.includes("/public/shares/demo-token/album")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => albumPayload
        });
      }
      if (url.includes("/public/shares/demo-token/assets")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => assetsPayload
        });
      }
      if (url.includes("/public/shares/demo-token/zip") && method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => zipStatusDone
        });
      }
      if (url.includes("/public/shares/demo-token/zip")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => zipStatusIdle
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({})
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/share/demo-token"]}>
        <App />
      </MemoryRouter>
    );

    const prepareButton = await screen.findByRole("button", { name: /prepare zip/i });
    await waitFor(() => expect(prepareButton).toBeEnabled());
    fireEvent.click(prepareButton);

    const downloadLink = await screen.findByRole("link", { name: /download zip/i });
    expect(downloadLink).toHaveAttribute(
      "href",
      expect.stringContaining("/public/shares/demo-token/zip/download")
    );
  });

  it("shows public ZIP errors when preparation fails", async () => {
    mockedSessionStatus.mockResolvedValue(false);

    const albumPayload = {
      id: "album-public-zip-error",
      title: "Error share",
      created_at: "2026-01-15T08:00:00Z",
      updated_at: "2026-01-15T08:00:00Z"
    };

    const assetsPayload = {
      items: []
    };

    const zipStatusIdle = {
      status: "idle",
      album_id: "album-public-zip-error",
      job_id: null,
      asset_count: null,
      zip_bytes: null,
      started_at: null,
      finished_at: null,
      created_at: null,
      invalidated_at: null,
      download_url: null,
      error: null
    };

    const fetchMock = vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      const method =
        (init?.method ?? (typeof input === "string" ? "GET" : input.method)).toUpperCase();
      if (url.includes("/public/shares/demo-token/album")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => albumPayload
        });
      }
      if (url.includes("/public/shares/demo-token/assets")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => assetsPayload
        });
      }
      if (url.includes("/public/shares/demo-token/zip") && method === "POST") {
        return Promise.resolve({
          ok: false,
          status: 500,
          statusText: "Server error",
          json: async () => ({ detail: "zip failed" })
        });
      }
      if (url.includes("/public/shares/demo-token/zip")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => zipStatusIdle
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({})
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/share/demo-token"]}>
        <App />
      </MemoryRouter>
    );

    const prepareButton = await screen.findByRole("button", { name: /prepare zip/i });
    await waitFor(() => expect(prepareButton).toBeEnabled());
    fireEvent.click(prepareButton);

    expect(await screen.findByRole("alert")).toHaveTextContent(/zip failed/i);
  });

  it("renders timeline cards for authenticated owners", async () => {
    mockedSessionStatus.mockResolvedValue(true);

    const assetPayload = {
      items: [
        {
          id: "asset-1",
          type: "photo",
          captured_at: "2026-01-20T16:30:00Z",
          created_at: "2026-01-20T16:30:00Z",
          duration_ms: null,
          width: 4032,
          height: 3024,
          live_photo_video_id: null
        },
        {
          id: "asset-2",
          type: "video",
          captured_at: "2026-01-18T09:05:00Z",
          created_at: "2026-01-18T09:05:00Z",
          duration_ms: 128000,
          width: 1920,
          height: 1080,
          live_photo_video_id: null
        },
        {
          id: "asset-3",
          type: "live_photo",
          captured_at: "2026-01-14T14:15:00Z",
          created_at: "2026-01-14T14:15:00Z",
          duration_ms: null,
          width: 3024,
          height: 4032,
          live_photo_video_id: "asset-3-video"
        }
      ],
      next_cursor: null
    };

    const albumPayload = {
      items: [
        {
          id: "album-1",
          title: "Favorites",
          created_at: "2026-01-19T10:00:00Z",
          updated_at: "2026-01-19T10:00:00Z",
          item_count: 2
        }
      ]
    };

    const fetchMock = vi.fn().mockImplementation((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/admin/index/overview")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => ({
            scan: { status: "idle", job_id: null },
            assets: { count: 0 },
            jobs: { metadata: {}, thumb: {}, transcode: {} },
            active_jobs: 0
          })
        });
      }
      const payload = url.includes("/albums") ? albumPayload : assetPayload;
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => payload
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(
      <MemoryRouter initialEntries={["/app/timeline"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText("Jan 20, 2026")).toBeInTheDocument();
    expect(screen.getByText("Photo")).toBeInTheDocument();
    expect(screen.getByText("Live Photo")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Photo thumbnail from Jan 20, 2026" })
    ).toHaveAttribute("src", expect.stringContaining("/assets/asset-1/thumb"));
    expect(container.querySelector("video.live-photo-video")).toBeInTheDocument();
  });

  it("applies date and location filters to timeline requests", async () => {
    mockedSessionStatus.mockResolvedValue(true);

    const assetPayload = {
      items: [],
      next_cursor: null
    };

    const albumPayload = {
      items: []
    };

    const assetUrls: string[] = [];
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/admin/index/overview")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => ({
            scan: { status: "idle", job_id: null },
            assets: { count: 0 },
            jobs: { metadata: {}, thumb: {}, transcode: {} },
            active_jobs: 0
          })
        });
      }
      if (url.includes("/assets?")) {
        assetUrls.push(url);
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => assetPayload
        });
      }
      if (url.includes("/albums")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => albumPayload
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({})
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/app/timeline"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByText(/no assets yet/i);

    fireEvent.change(screen.getByLabelText(/start date/i), {
      target: { value: "2026-01-01" }
    });
    fireEvent.change(screen.getByLabelText(/end date/i), {
      target: { value: "2026-01-10" }
    });
    fireEvent.change(screen.getByLabelText(/min lat/i), {
      target: { value: "40" }
    });
    fireEvent.change(screen.getByLabelText(/min lon/i), {
      target: { value: "-120" }
    });
    fireEvent.change(screen.getByLabelText(/max lat/i), {
      target: { value: "42" }
    });
    fireEvent.change(screen.getByLabelText(/max lon/i), {
      target: { value: "-118" }
    });
    fireEvent.click(screen.getByRole("button", { name: /apply filters/i }));

    await waitFor(() => {
      expect(assetUrls.length).toBeGreaterThan(1);
    });

    const lastUrl = assetUrls[assetUrls.length - 1];
    const params = new URL(lastUrl, "http://localhost").searchParams;
    expect(params.get("start")).toBe("2026-01-01T00:00:00.000Z");
    expect(params.get("end")).toBe("2026-01-10T23:59:59.999Z");
    expect(params.get("min_lat")).toBe("40");
    expect(params.get("min_lon")).toBe("-120");
    expect(params.get("max_lat")).toBe("42");
    expect(params.get("max_lon")).toBe("-118");
  });

  it("creates and revokes share links from album detail", async () => {
    mockedSessionStatus.mockResolvedValue(true);

    const albumPayload = {
      id: "album-1",
      title: "Road trip",
      created_at: "2026-01-12T08:00:00Z",
      updated_at: "2026-01-18T08:00:00Z",
      item_count: 0
    };

    const assetsPayload = { items: [] };

    let shareItems = [
      {
        id: "share-1",
        album_id: "album-1",
        token: "token-1",
        created_at: "2026-01-18T12:00:00Z",
        revoked_at: null
      }
    ];

    const newShare = {
      id: "share-2",
      album_id: "album-1",
      token: "token-2",
      created_at: "2026-01-19T12:00:00Z",
      revoked_at: null
    };

    const revokedShare = {
      ...shareItems[0],
      revoked_at: "2026-01-20T12:00:00Z"
    };

    const fetchMock = vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      const method = init?.method ?? "GET";
      if (url.includes("/albums/album-1/shares") && method === "GET") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => ({ items: shareItems })
        });
      }
      if (url.includes("/albums/album-1/shares") && method === "POST") {
        shareItems = [newShare, ...shareItems];
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => newShare
        });
      }
      if (url.includes("/albums/album-1/shares/share-1") && method === "DELETE") {
        shareItems = shareItems.map((share) => (share.id === "share-1" ? revokedShare : share));
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => revokedShare
        });
      }
      if (url.includes("/albums/album-1/assets")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => assetsPayload
        });
      }
      if (url.includes("/albums/album-1")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => albumPayload
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({})
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true
    });

    render(
      <MemoryRouter initialEntries={["/app/albums/album-1"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText(/manage access/i)).toBeInTheDocument();
    expect(await screen.findByText(/token-1/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /new share link/i }));
    expect(await screen.findByText(/token-2/i)).toBeInTheDocument();

    const copyButtons = screen.getAllByRole("button", { name: /copy link/i });
    fireEvent.click(copyButtons[0]);
    const expectedUrl = `${window.location.origin}/share/token-2`;
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(expectedUrl);
    });

    const revokeButtons = screen.getAllByRole("button", { name: /revoke/i });
    fireEvent.click(revokeButtons[1]);

    expect(await screen.findByText(/access revoked/i)).toBeInTheDocument();
  });
});
