import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { AlbumsView } from "./views/AlbumsView";
import { SignInView } from "./views/SignInView";
import { TimelineView } from "./views/TimelineView";
import { ViewerView } from "./views/ViewerView";

function AuthGate() {
  const { status } = useAuth();

  if (status === "checking") {
    return (
      <section className="signin">
        <div className="signin-card">
          <p className="eyebrow">Checking session</p>
          <h1>Warming up your library</h1>
          <p className="subhead">Looking for an owner session.</p>
        </div>
      </section>
    );
  }

  if (status === "unauthenticated") {
    return <SignInView />;
  }

  return <Outlet />;
}

function OwnerLayout() {
  const { signOut } = useAuth();

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <p className="eyebrow">MyPhotos</p>
            <h2>Owner console</h2>
          </div>
        </div>
        <nav className="nav-links">
          <NavLink
            to="/app/timeline"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Timeline
          </NavLink>
          <NavLink
            to="/app/albums"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Albums
          </NavLink>
          <NavLink
            to="/app/viewer"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Viewer
          </NavLink>
        </nav>
        <button className="ghost" onClick={signOut}>
          Sign out
        </button>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

function NotFound() {
  return (
    <section className="page">
      <h1>Route not found</h1>
      <p className="subhead">Double-check the path or head back to the timeline.</p>
    </section>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/app/timeline" replace />} />
        <Route path="/app" element={<AuthGate />}>
          <Route element={<OwnerLayout />}>
            <Route index element={<Navigate to="timeline" replace />} />
            <Route path="timeline" element={<TimelineView />} />
            <Route path="albums" element={<AlbumsView />} />
            <Route path="viewer" element={<ViewerView />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AuthProvider>
  );
}
