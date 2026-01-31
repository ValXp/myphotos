const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type RegistrationOptionsResponse = {
  rp: { id: string; name: string };
  user: { id: string; name: string; displayName: string };
  challenge: string;
  pubKeyCredParams: { type: string; alg: number }[];
  timeout: number;
  attestation: AttestationConveyancePreference;
  excludeCredentials: Array<{ id: string; type: string; transports?: string[] }>;
};

type LoginOptionsResponse = {
  challenge: string;
  timeout: number;
  rpId: string;
  allowCredentials: Array<{ id: string; type: string; transports?: string[] }>;
  userVerification?: UserVerificationRequirement;
};

type RegistrationVerifyPayload = {
  credential: Record<string, unknown>;
  transports?: string[];
};

type LoginVerifyPayload = {
  credential: Record<string, unknown>;
};

type StatusResponse = { status: string; user_id?: string };

function toBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function parseSignCount(authenticatorData: ArrayBuffer): number {
  if (authenticatorData.byteLength < 37) {
    return 0;
  }
  const view = new DataView(authenticatorData);
  return view.getUint32(33, false);
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
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

export function isPasskeySupported(): boolean {
  return typeof window !== "undefined" &&
    typeof window.PublicKeyCredential !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.credentials;
}

export function isSecureContext(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.isSecureContext;
}

export async function fetchSessionStatus(): Promise<boolean> {
  try {
    await requestJson<StatusResponse>("/auth/session", { method: "GET" });
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return false;
    }
    throw error;
  }
}

export async function logout(): Promise<void> {
  await requestJson<StatusResponse>("/auth/logout", { method: "POST" });
}

export async function registerPasskey(displayName: string): Promise<void> {
  console.log("passkey.register.step", "request_options");
  const options = await requestJson<RegistrationOptionsResponse>("/auth/webauthn/register/options", {
    method: "POST",
    body: JSON.stringify({ display_name: displayName })
  });
  console.log("passkey.register.step", "options_ok", {
    rp: options.rp,
    timeout: options.timeout,
    attestation: options.attestation,
  });

  const publicKey: PublicKeyCredentialCreationOptions = {
    rp: options.rp,
    user: {
      id: fromBase64Url(options.user.id),
      name: options.user.name,
      displayName: options.user.displayName
    },
    challenge: fromBase64Url(options.challenge),
    pubKeyCredParams: options.pubKeyCredParams,
    timeout: options.timeout,
    attestation: options.attestation,
    excludeCredentials: options.excludeCredentials.map((item) => ({
      id: fromBase64Url(item.id),
      type: item.type as PublicKeyCredentialType,
      transports: item.transports as AuthenticatorTransport[] | undefined
    }))
  };

  console.log("passkey.register.step", "calling_navigator_credentials_create");
  let credential: PublicKeyCredential | null = null;
  try {
    credential = (await navigator.credentials.create({
      publicKey
    })) as PublicKeyCredential | null;
  } catch (err) {
    console.error("passkey.register.step", "navigator_credentials_create_failed", err);
    throw err;
  }
  console.log("passkey.register.step", "credential_create_returned", {
    hasCredential: !!credential,
  });

  if (!credential) {
    throw new Error("Passkey creation was canceled.");
  }

  console.log("passkey.register.step", "credential_ok", {
    type: credential.type,
    id: credential.id,
  });

  const response = credential.response as AuthenticatorAttestationResponse & {
    getPublicKey?: () => ArrayBuffer | null;
    getTransports?: () => string[];
  };

  const responseJson = {
    clientDataJSON: toBase64Url(response.clientDataJSON),
    attestationObject: toBase64Url(response.attestationObject)
  };

  // Transports is optional and not supported consistently.
  let transports: string[] | undefined;
  try {
    transports = (response as any).getTransports ? (response as any).getTransports() : undefined;
    console.log("passkey.register.step", "got_transports", { transports });
  } catch (err) {
    console.warn("passkey.register.step", "getTransports_failed", err);
    transports = undefined;
  }

  const credentialJson = {
    id: credential.id,
    rawId: credential.id,
    type: credential.type,
    response: responseJson
  };

  const payload: RegistrationVerifyPayload = {
    credential: credentialJson,
    transports
  };

  console.log("passkey.register.step", "posting_register_verify");
  await requestJson<StatusResponse>("/auth/webauthn/register/verify", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  console.log("passkey.register.step", "register_verify_ok");
}


export async function signInWithPasskey(): Promise<void> {
  const options = await requestJson<LoginOptionsResponse>("/auth/webauthn/login/options", {
    method: "POST"
  });

  const publicKey: PublicKeyCredentialRequestOptions = {
    challenge: fromBase64Url(options.challenge),
    timeout: options.timeout,
    rpId: options.rpId,
    allowCredentials: options.allowCredentials.map((item) => ({
      id: fromBase64Url(item.id),
      type: item.type as PublicKeyCredentialType,
      transports: item.transports as AuthenticatorTransport[] | undefined
    })),
    userVerification: options.userVerification
  };

  const credential = (await navigator.credentials.get({
    publicKey
  })) as PublicKeyCredential | null;

  if (!credential) {
    throw new Error("Passkey sign-in was canceled.");
  }

  const response = credential.response as AuthenticatorAssertionResponse;

  const responseJson = {
    clientDataJSON: toBase64Url(response.clientDataJSON),
    authenticatorData: toBase64Url(response.authenticatorData),
    signature: toBase64Url(response.signature),
    userHandle: response.userHandle ? toBase64Url(response.userHandle) : null,
  };

  const credentialJson = {
    id: credential.id,
    rawId: credential.id,
    type: credential.type,
    response: responseJson,
  };

  const payload: LoginVerifyPayload = {
    credential: credentialJson,
  };

  await requestJson<StatusResponse>("/auth/webauthn/login/verify", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
