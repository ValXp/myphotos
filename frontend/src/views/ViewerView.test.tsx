import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ViewerView } from "./ViewerView";

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

function responseJson(payload: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload
  } as unknown as Response;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("ViewerView", () => {
  it("loads assets and renders the viewer shell", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      responseJson({
        items: [],
        next_cursor: null
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <ViewerView />
      </MemoryRouter>
    );

    expect(await screen.findByText("Owner viewer")).toBeInTheDocument();
    expect(
      screen.getByText(/no assets yet\. add photos or videos to start viewing\./i)
    ).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/assets?"),
      expect.objectContaining({ method: "GET", credentials: "include" })
    );
  });
});
