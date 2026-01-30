import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  ApiError,
  isPasskeySupported,
  isSecureContext,
  registerPasskey,
  signInWithPasskey
} from "../auth/webauthn";

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") {
      return "Passkey prompt dismissed.";
    }
    if (error.name === "NotSupportedError") {
      return "Passkeys are not supported in this browser.";
    }
    return error.message || "Passkey request failed.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

export function SignInView() {
  const { completeSignIn } = useAuth();
  const [displayName, setDisplayName] = useState("Owner");
  const [busyAction, setBusyAction] = useState<"register" | "login" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const passkeySupported = isPasskeySupported();
  const secureContext = isSecureContext();
  const canUsePasskeys = passkeySupported && secureContext;

  const handleRegister = async () => {
    if (!canUsePasskeys || busyAction) {
      return;
    }
    const trimmedName = displayName.trim() || "Owner";
    setBusyAction("register");
    setError(null);
    setNotice(null);
    try {
      await registerPasskey(trimmedName);
      setNotice("Passkey created. Sign in to continue.");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusyAction(null);
    }
  };

  const handleLogin = async () => {
    if (!canUsePasskeys || busyAction) {
      return;
    }
    setBusyAction("login");
    setError(null);
    setNotice(null);
    try {
      await signInWithPasskey();
      completeSignIn();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <section className="signin">
      <div className="signin-card stagger">
        <p className="eyebrow">Owner access</p>
        <h1>Unlock your library</h1>
        <p className="subhead">
          Sign in with a passkey to unlock the owner console. First time here?
          Create a passkey to get started.
        </p>
        {!secureContext && (
          <div className="status error" role="status">
            Passkeys require HTTPS or localhost. Switch to a secure origin to continue.
          </div>
        )}
        {!passkeySupported && (
          <div className="status error" role="status">
            This browser does not support passkeys. Try a modern Chromium or Safari build.
          </div>
        )}
        {error && (
          <div className="status error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="status success" role="status">
            {notice}
          </div>
        )}
        <div className="signin-grid">
          <div className="signin-panel">
            <h3>Create a passkey</h3>
            <p className="hint">Register the first owner passkey for this library.</p>
            <label className="field">
              <span>Display name</span>
              <input
                className="text-input"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                disabled={!!busyAction}
              />
            </label>
            <button
              className="primary"
              onClick={handleRegister}
              disabled={!canUsePasskeys || !!busyAction}
            >
              {busyAction === "register" ? "Creating passkey..." : "Create passkey"}
            </button>
          </div>
          <div className="signin-panel">
            <h3>Sign in</h3>
            <p className="hint">Use your existing passkey to unlock the owner console.</p>
            <button
              className="ghost"
              onClick={handleLogin}
              disabled={!canUsePasskeys || !!busyAction}
            >
              {busyAction === "login" ? "Waiting for passkey..." : "Sign in with passkey"}
            </button>
          </div>
        </div>
        <div className="signin-footer">
          <span className="hint">Passkey cookies stay on this device until you sign out.</span>
        </div>
      </div>
    </section>
  );
}
