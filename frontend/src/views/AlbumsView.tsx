import type { CSSProperties } from "react";

const albums = [
  { title: "Summer 2024", count: "214 items" },
  { title: "Roadtrip", count: "88 items" },
  { title: "Studio sets", count: "46 items" },
  { title: "Family", count: "173 items" }
];

export function AlbumsView() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Owner albums</p>
          <h1>Albums</h1>
          <p className="subhead">Create, sort, and share your curated sets.</p>
        </div>
        <button className="primary">New album</button>
      </header>
      <div className="grid stagger">
        {albums.map((album, index) => (
          <article
            key={album.title}
            className="album-card"
            style={{ "--delay": `${index * 0.08}s` } as CSSProperties}
          >
            <div className="album-cover" aria-hidden="true" />
            <div className="media-meta">
              <h3>{album.title}</h3>
              <p>{album.count}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
