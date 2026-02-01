import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";

const webauthnMocks = vi.hoisted(() => ({
  fetchSessionStatus: vi.fn<[], Promise<boolean>>(),
  logout: vi.fn<[], Promise<void>>()
}));

vi.mock("./webauthn", () => {
  return {
    fetchSessionStatus: webauthnMocks.fetchSessionStatus,
    logout: webauthnMocks.logout
  };
});

function Consumer() {
  const { status, completeSignIn, signOut, refreshSession } = useAuth();
  return (
    <div>
      <p data-testid="status">{status}</p>
      <button onClick={completeSignIn}>Complete</button>
      <button onClick={() => void refreshSession()}>Refresh</button>
      <button onClick={() => void signOut()}>Sign out</button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuthProvider", () => {
  it("marks authenticated sessions", async () => {
    webauthnMocks.fetchSessionStatus.mockResolvedValue(true);

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    });
  });

  it("falls back to unauthenticated when session check fails", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    webauthnMocks.fetchSessionStatus.mockRejectedValue(new Error("offline"));

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    });
    expect(warn).toHaveBeenCalled();
  });

  it("signOut always clears status even when logout fails", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    webauthnMocks.fetchSessionStatus.mockResolvedValue(true);
    webauthnMocks.logout.mockRejectedValue(new Error("server"));

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await screen.findByText("authenticated");

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    });
    expect(warn).toHaveBeenCalled();
  });

  it("completeSignIn updates status without hitting the network", async () => {
    webauthnMocks.fetchSessionStatus.mockResolvedValue(false);

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );

    await screen.findByText("unauthenticated");

    fireEvent.click(screen.getByRole("button", { name: /complete/i }));

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    });
  });
});

describe("useAuth", () => {
  it("throws when used outside the provider", () => {
    function BadConsumer() {
      useAuth();
      return null;
    }

    // React logs render errors even when assertions catch them.
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<BadConsumer />)).toThrow(/within AuthProvider/i);
    spy.mockRestore();
  });
});
