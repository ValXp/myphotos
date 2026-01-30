import { useAuth } from "../auth/AuthContext";

export function SignInView() {
  const { signIn } = useAuth();

  return (
    <section className="signin">
      <div className="signin-card">
        <p className="eyebrow">Owner access</p>
        <h1>Unlock your library</h1>
        <p className="subhead">
          Passkey sign-in will live here. For now, use the demo gate to see the
          owner shell.
        </p>
        <div className="signin-actions">
          <button className="primary" onClick={signIn}>
            Enter demo mode
          </button>
          <span className="hint">Auth flow ships in the next step.</span>
        </div>
      </div>
    </section>
  );
}
