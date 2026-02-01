import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  fetchSessionStatus,
  isPasskeySupported,
  isSecureContext,
  logout,
  registerPasskey,
  signInWithPasskey
} from "./webauthn";

function responseJson(payload: unknown, init: Partial<Response> = {}) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
    ...init
  } as unknown as Response;
}

function responseError(
  status: number,
  statusText: string,
  payload: unknown,
  init: Partial<Response> = {}
) {
  return {
    ok: false,
    status,
    statusText,
    json: async () => payload,
    ...init
  } as unknown as Response;
}

const originalPublicKeyCredential = (globalThis as any).PublicKeyCredential;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  (globalThis as any).PublicKeyCredential = originalPublicKeyCredential;
});

describe("webauthn utilities", () => {
  it("detects passkey support", () => {
    delete (globalThis as any).PublicKeyCredential;
    Object.defineProperty(navigator, "credentials", { value: undefined, configurable: true });
    expect(isPasskeySupported()).toBe(false);

    (globalThis as any).PublicKeyCredential = function PublicKeyCredential() {
      // noop
    };
    Object.defineProperty(navigator, "credentials", { value: {}, configurable: true });
    expect(isPasskeySupported()).toBe(true);
  });

  it("reports secure context via the window flag", () => {
    Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
    expect(isSecureContext()).toBe(true);
  });
});

describe("webauthn API calls", () => {
  beforeEach(() => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  it("fetchSessionStatus returns true when session endpoint succeeds", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseJson({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchSessionStatus()).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/auth/session",
      expect.objectContaining({ method: "GET", credentials: "include" })
    );
  });

  it("fetchSessionStatus returns false on 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(responseError(401, "Unauthorized", { detail: "no session" }))
    );

    await expect(fetchSessionStatus()).resolves.toBe(false);
  });

  it("fetchSessionStatus propagates non-401 errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(responseError(500, "Server error", { detail: "boom" }))
    );

    await expect(fetchSessionStatus()).rejects.toBeInstanceOf(ApiError);
    await expect(fetchSessionStatus()).rejects.toMatchObject({ status: 500 });
  });

  it("logout issues a POST request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(responseJson({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await logout();

    expect(fetchMock).toHaveBeenCalledWith(
      "/auth/logout",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });

  it("registerPasskey posts credential payload", async () => {
    const options = {
      rp: { id: "localhost", name: "myphotos" },
      user: { id: "AQIDBA", name: "user", displayName: "User" },
      challenge: "AQIDBA",
      pubKeyCredParams: [{ type: "public-key", alg: -7 }],
      timeout: 60000,
      attestation: "none" as const,
      excludeCredentials: []
    };

    const clientDataJSON = new Uint8Array([5, 6]).buffer;
    const attestationObject = new Uint8Array([7, 8, 9]).buffer;

    Object.defineProperty(navigator, "credentials", {
      configurable: true,
      value: {
        create: vi.fn().mockResolvedValue({
          id: "cred-1",
          type: "public-key",
          response: {
            clientDataJSON,
            attestationObject,
            getTransports: () => ["usb"]
          }
        })
      }
    });

    const seenBodies: any[] = [];
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/auth/webauthn/register/options")) {
        return Promise.resolve(responseJson(options));
      }
      if (url.includes("/auth/webauthn/register/verify")) {
        if (init?.body) {
          seenBodies.push(JSON.parse(String(init.body)));
        }
        return Promise.resolve(responseJson({ status: "ok" }));
      }
      return Promise.resolve(responseJson({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    await registerPasskey("User");

    expect(fetchMock).toHaveBeenCalled();
    expect(seenBodies).toHaveLength(1);
    const body = seenBodies[0];
    expect(body.credential.id).toBe("cred-1");
    expect(body.transports).toEqual(["usb"]);
    expect(body.credential.response.clientDataJSON).toBeDefined();
    expect(body.credential.response.attestationObject).toBeDefined();
  });

  it("registerPasskey surfaces cancellation", async () => {
    Object.defineProperty(navigator, "credentials", {
      configurable: true,
      value: {
        create: vi.fn().mockResolvedValue(null)
      }
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        responseJson({
          rp: { id: "localhost", name: "myphotos" },
          user: { id: "AQIDBA", name: "user", displayName: "User" },
          challenge: "AQIDBA",
          pubKeyCredParams: [{ type: "public-key", alg: -7 }],
          timeout: 60000,
          attestation: "none" as const,
          excludeCredentials: []
        })
      )
    );

    await expect(registerPasskey("User")).rejects.toThrow(/canceled/i);
  });

  it("signInWithPasskey posts assertion payload", async () => {
    const options = {
      challenge: "AQIDBA",
      timeout: 60000,
      rpId: "localhost",
      allowCredentials: [{ id: "AQIDBA", type: "public-key", transports: ["usb"] }],
      userVerification: "preferred" as const
    };

    const responseBuffers = {
      clientDataJSON: new Uint8Array([1]).buffer,
      authenticatorData: new Uint8Array([2]).buffer,
      signature: new Uint8Array([3]).buffer,
      userHandle: null as ArrayBuffer | null
    };

    Object.defineProperty(navigator, "credentials", {
      configurable: true,
      value: {
        get: vi.fn().mockResolvedValue({
          id: "cred-1",
          type: "public-key",
          response: responseBuffers
        })
      }
    });

    const seenBodies: any[] = [];
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/auth/webauthn/login/options")) {
        return Promise.resolve(responseJson(options));
      }
      if (url.includes("/auth/webauthn/login/verify")) {
        if (init?.body) {
          seenBodies.push(JSON.parse(String(init.body)));
        }
        return Promise.resolve(responseJson({ status: "ok" }));
      }
      return Promise.resolve(responseJson({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    await signInWithPasskey();

    expect(seenBodies).toHaveLength(1);
    const body = seenBodies[0];
    expect(body.credential.id).toBe("cred-1");
    expect(body.credential.response.userHandle).toBeNull();
  });
});
