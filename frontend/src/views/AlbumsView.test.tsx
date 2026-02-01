import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlbumsView } from "./AlbumsView";

const authMocks = vi.hoisted(() => ({
  refreshSession: vi.fn()
}));

vi.mock("../auth/AuthContext", () => {
  return {
    useAuth: () => ({
      refreshSession: authMocks.refreshSession
    })
  };
});

function responseJson(payload: unknown, init: Partial<Response> = {}) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
    ...init
  } as unknown as Response;
}

function responseError(status: number, statusText: string, payload: unknown) {
  return {
    ok: false,
    status,
    statusText,
    json: async () => payload
  } as unknown as Response;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("AlbumsView", () => {
  it("loads albums and renders formatted metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      responseJson({
        items: [
          {
            id: "album-1",
            title: "Favorites",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
            item_count: 1
          }
        ]
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    expect(await screen.findByText("Favorites")).toBeInTheDocument();
    // Item count appears both on the cover and in the meta line; assert the meta format.
    expect(screen.getByText(/1 item · updated/i)).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      "/albums",
      expect.objectContaining({ method: "GET", credentials: "include" })
    );
  });

  it("creates an album and reloads", async () => {
    const promptMock = vi.spyOn(window, "prompt").mockReturnValue("  Road trip  ");

    let getCount = 0;
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (url === "/albums" && method === "GET") {
        getCount += 1;
        if (getCount === 1) {
          return Promise.resolve(responseJson({ items: [] }));
        }
        return Promise.resolve(
          responseJson({
            items: [
              {
                id: "album-1",
                title: "Road trip",
                created_at: "2026-01-01T00:00:00Z",
                updated_at: null,
                item_count: 0
              }
            ]
          })
        );
      }
      if (url === "/albums" && method === "POST") {
        return Promise.resolve(
          responseJson({
            id: "album-1",
            title: "Road trip",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: null,
            item_count: 0
          })
        );
      }
      return Promise.resolve(responseJson({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    expect(await screen.findByText(/no albums yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /new album/i }));

    expect(await screen.findByText("Road trip")).toBeInTheDocument();
    expect(promptMock).toHaveBeenCalled();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/albums",
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("refreshes session on 401 errors", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(responseError(401, "Unauthorized", { detail: "no session" }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <AlbumsView />
      </MemoryRouter>
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/no session/i);

    await waitFor(() => {
      expect(authMocks.refreshSession).toHaveBeenCalled();
    });
  });
});
