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

    render(
      <MemoryRouter initialEntries={["/share/demo-token"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText(/public share/i)).toBeInTheDocument();
    expect(screen.getByText(/demo-token/i)).toBeInTheDocument();
    expect(screen.queryByText(/unlock your library/i)).not.toBeInTheDocument();
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
});
