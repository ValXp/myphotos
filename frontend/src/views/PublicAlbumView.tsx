import { useMemo } from "react";
import { useParams } from "react-router-dom";

function formatToken(token: string | undefined): string {
  if (!token) {
    return "unknown";
  }
  if (token.length <= 10) {
    return token;
  }
  return `${token.slice(0, 6)}...${token.slice(-4)}`;
}

export function PublicAlbumView() {
  const { token } = useParams();
  const tokenLabel = useMemo(() => formatToken(token), [token]);

  return (
    <section className="public-page">
      <header className="public-hero">
        <div className="public-hero-copy">
          <p className="eyebrow">Shared album</p>
          <h1>Welcome to a public share</h1>
          <p className="subhead">
            This album lives outside the owner console, so anyone with the link can
            browse it.
          </p>
        </div>
        <div className="public-token-card" aria-live="polite">
          <p className="eyebrow">Share token</p>
          <p className="public-token-value">{tokenLabel}</p>
          <p className="hint">Keep this link handy for quick returns.</p>
        </div>
      </header>
      <div className="public-panels">
        <article className="public-panel">
          <h2>Album highlights</h2>
          <p className="subhead">
            Public album details and grid previews will appear here next.
          </p>
        </article>
        <article className="public-panel accent">
          <h2>Ready to download?</h2>
          <p className="subhead">
            Shared downloads and playback will live in this public space.
          </p>
          <button className="primary" type="button" disabled>
            Download placeholder
          </button>
        </article>
      </div>
    </section>
  );
}
