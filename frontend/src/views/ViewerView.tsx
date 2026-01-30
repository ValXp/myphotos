export function ViewerView() {
  return (
    <section className="page viewer">
      <div className="viewer-stage">
        <div className="viewer-frame" aria-hidden="true" />
        <div className="viewer-controls">
          <button className="ghost">Prev</button>
          <button className="ghost">Next</button>
        </div>
      </div>
      <div className="viewer-meta">
        <h1>Viewer</h1>
        <p className="subhead">A focused canvas for photos, Live Photos, and video.</p>
        <div className="pill-group">
          <span className="pill">Zoom 100%</span>
          <span className="pill">Playback ready</span>
        </div>
      </div>
    </section>
  );
}
