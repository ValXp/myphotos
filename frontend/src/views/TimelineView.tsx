import type { CSSProperties } from "react";

const cards = [
  { title: "Morning walk", meta: "54 items" },
  { title: "City lights", meta: "18 items" },
  { title: "Studio", meta: "27 items" },
  { title: "Weekend hike", meta: "42 items" },
  { title: "Family", meta: "31 items" },
  { title: "Favorites", meta: "12 items" }
];

export function TimelineView() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Owner timeline</p>
          <h1>Timeline</h1>
          <p className="subhead">Newest-first cards with room for filters and paging.</p>
        </div>
        <div className="pill-group">
          <span className="pill">All dates</span>
          <span className="pill">Anywhere</span>
        </div>
      </header>
      <div className="grid stagger">
        {cards.map((card, index) => (
          <article
            key={card.title}
            className="media-card"
            style={{ "--delay": `${index * 0.06}s` } as CSSProperties}
          >
            <div className="media-thumb" aria-hidden="true" />
            <div className="media-meta">
              <h3>{card.title}</h3>
              <p>{card.meta}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
