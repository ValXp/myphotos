import { render, screen } from "@testing-library/react";
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
        }
      ],
      next_cursor: null
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => assetPayload
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/app/timeline"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText("Jan 20, 2026")).toBeInTheDocument();
    expect(screen.getByText("Photo")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Photo thumbnail from Jan 20, 2026" })
    ).toHaveAttribute("src", expect.stringContaining("/assets/asset-1/thumb"));
  });
});
