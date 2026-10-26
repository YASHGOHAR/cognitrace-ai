import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, clearAuth, mockMode } from "./api/client";
import type { Analysis, Message, Pattern, Route, Session, User } from "./types";

const iconPaths: Record<string, string> = {
  overview: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z",
  sessions: "M4 5h16M4 10h16M4 15h10M4 20h7",
  analysis: "M4 19V5m0 14h16M7 15l4-4 3 2 6-7",
  patterns:
    "M12 3v4m0 10v4M3 12h4m10 0h4M5.64 5.64l2.83 2.83m7.06 7.06 2.83 2.83m0-12.72-2.83 2.83m-7.06 7.06-2.83 2.83",
  recommendations:
    "M9 18h6m-5 4h4m-4-8a6 6 0 1 1 4 0c-.7.6-1 1.2-1 2h-2c0-.8-.3-1.4-1-2z",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm0-5v2m0 14v2m9-9h-2M5 12H3m15.36-6.36-1.42 1.42M7.06 16.94l-1.42 1.42m12.72 0-1.42-1.42M7.06 7.06 5.64 5.64",
  plus: "M12 5v14m-7-7h14",
  arrow: "M5 12h14m-7-7 7 7-7 7",
  search: "m20 20-4.5-4.5M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0",
  chevron: "m9 18 6-6-6-6",
  spark:
    "m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3zm7 11 .9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9L19 14z",
  close: "M18 6 6 18M6 6l12 12",
  clock: "M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
  menu: "M4 6h16M4 12h16M4 18h16",
  send: "m22 2-7 20-4-9-9-4 20-7zM22 2 11 13",
  check: "m5 12 4 4L19 6",
  trend: "M3 17l6-6 4 4 8-8m-6 0h6v6",
};
function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={iconPaths[name] ?? iconPaths.spark} />
    </svg>
  );
}
const navItems: { id: Route; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "sessions", label: "My sessions", icon: "sessions" },
  { id: "analysis", label: "Reflections", icon: "analysis" },
  { id: "patterns", label: "Patterns", icon: "patterns" },
  { id: "recommendations", label: "For you", icon: "recommendations" },
];
const shortDate = (value: string) => value.split(" · ")[0];

export default function App() {
  const [route, setRoute] = useState<Route>(() =>
    import.meta.env.VITE_USE_MOCK_API === "false"
      ? "auth"
      : (location.hash.replace("#/", "") as Route) || "overview",
  );
  const [sessions, setSessions] = useState<Session[]>([]),
    [user, setUser] = useState<User | null>(null);
  const [patterns, setPatterns] = useState<Pattern[]>([]),
    [recommendations, setRecommendations] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null),
    [activeSession, setActiveSession] = useState("s-101");
  const [query, setQuery] = useState(""),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [modal, setModal] = useState(false),
    [mobileOpen, setMobileOpen] = useState(false),
    [toast, setToast] = useState("");
  const [consent, setConsent] = useState(
    () => localStorage.getItem("cognitrace.demo.consent") !== "false",
  );
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const onHash = () =>
      setRoute((location.hash.replace("#/", "") as Route) || "overview");
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (route === "auth") {
      setLoading(false);
      return;
    }
    Promise.all([
      api.me(),
      api.sessions(),
      api.patterns(),
      api.recommendations(),
    ])
      .then(([u, s, p, r]) => {
        setUser(u);
        setSessions(s);
        setPatterns(p);
        setRecommendations(r);
      })
      .catch((e) =>
        setError(
          e instanceof Error ? e.message : "Could not load your workspace.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (route === "analysis" && activeSession)
      api
        .analysis(activeSession)
        .then(setAnalysis)
        .catch((e) =>
          setError(
            e instanceof Error ? e.message : "Could not load this reflection.",
          ),
        );
  }, [route, activeSession]);
  const navigate = (next: Route) => {
    setRoute(next);
    location.hash = `/${next}`;
    setMobileOpen(false);
    setError("");
  };
  const current =
    sessions.find((item) => item.id === activeSession) ?? sessions[0];
  const filtered = useMemo(
    () =>
      sessions.filter((session) =>
        `${session.title} ${session.topic}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [sessions, query],
  );
  const notify = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(""), 2800);
  };
  const startSession = async (title: string) => {
    setBusy(true);
    try {
      const session = await api.createSession(title);
      setSessions(await api.sessions());
      setActiveSession(session.id);
      navigate("chat");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start a session.");
    } finally {
      setBusy(false);
      setModal(false);
    }
  };
  const submitMessage = async (text: string) => {
    if (!current || !text.trim()) return;
    setBusy(true);
    try {
      const messages = await api.sendMessage(current.id, text.trim());
      setSessions(await api.sessions());
      setSessions((value) =>
        value.map((item) =>
          item.id === current.id ? { ...item, messages } : item,
        ),
      );
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Your message could not be sent.",
      );
    } finally {
      setBusy(false);
    }
  };
  const completeSession = async () => {
    if (!current) return;
    setBusy(true);
    try {
      const completedId = await api.completeSession(current.id);
      setSessions(await api.sessions());
      setActiveSession(completedId);
      setPatterns(await api.patterns());
      setAnalysis(await api.analysis(completedId));
      navigate("analysis");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not complete this session.",
      );
    } finally {
      setBusy(false);
    }
  };
  const sendFeedback = async (id: string, value: "helpful" | "not_helpful") => {
    if (!mockMode) {
      setError("Feedback saving is not available in the backend yet.");
      return;
    }
    try {
      await api.feedback(id, value);
      notify("Thanks for helping improve this reflection.");
    } catch {
      setError("Feedback could not be saved.");
    }
  };
  if (loading && route !== "auth")
    return (
      <div className="loading-screen">
        <div className="brand-mark">
          <Icon name="spark" size={20} />
        </div>
        <span>Preparing your reflection space…</span>
      </div>
    );
  if (route === "auth")
    return (
      <AuthPage
        busy={busy}
        error={error}
        onSubmit={async (email, password, name) => {
          setBusy(true);
          try {
            setUser(await api.authenticate(email, password, name));
            const [s, p, r] = await Promise.all([
              api.sessions(),
              api.patterns(),
              api.recommendations(),
            ]);
            setSessions(s);
            setPatterns(p);
            setRecommendations(r);
            navigate("overview");
          } catch (e) {
            setError(e instanceof Error ? e.message : "Could not sign in.");
          } finally {
            setBusy(false);
          }
        }}
      />
    );

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <a className="brand" href="#/overview">
          <span className="brand-mark">
            <Icon name="spark" size={19} />
          </span>
          <span className="brand-name">
            cognitrace<span className="brand-dot">.</span>
            <small>YOUR THINKING, IN VIEW</small>
          </span>
        </a>
        <div className="side-label">WORKSPACE</div>
        <nav className="side-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => navigate(item.id)}
              className={`nav-item ${route === item.id || (item.id === "sessions" && route === "chat") ? "selected" : ""}`}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.id === "patterns" && (
                <span className="nav-count">{patterns.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="side-label recent-label">
          RECENT SESSIONS{" "}
          <button aria-label="Start a session" onClick={() => setModal(true)}>
            <Icon name="plus" size={15} />
          </button>
        </div>
        <div className="recent-list">
          {sessions.slice(0, 4).map((item) => (
            <button
              key={item.id}
              className="recent-item"
              onClick={() => {
                setActiveSession(item.id);
                navigate(item.status === "in_progress" ? "chat" : "analysis");
              }}
            >
              <span className="recent-bullet" />
              <span className="recent-text">
                {item.title}
                <small>{shortDate(item.date)}</small>
              </span>
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <span className="privacy-icon">
              <Icon name="lock" size={15} />
            </span>
            <div>
              <strong>Your space, your choice</strong>
              <p>
                Your reflections stay yours. You can change data settings
                anytime.
              </p>
              <button onClick={() => navigate("settings")}>
                Privacy settings <Icon name="arrow" size={12} />
              </button>
            </div>
          </div>
          <button
            className="profile-switch"
            onClick={() => navigate("settings")}
          >
            <span className="avatar">
              {user?.name
                ?.split(" ")
                .map((p) => p[0])
                .join("") ?? "AM"}
            </span>
            <span className="profile-name">
              {user?.name ?? "Alex Morgan"}
              <small>Personal workspace</small>
            </span>
            <span className="profile-dots">···</span>
          </button>
        </div>
      </aside>
      {mobileOpen && (
        <button
          className="mobile-scrim"
          onClick={() => setMobileOpen(false)}
          aria-label="Close menu"
        />
      )}
      <main className="main-panel">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Icon name="menu" />
          </button>
          <div className="breadcrumbs">
            Workspace <Icon name="chevron" size={14} />
            <strong>{routeTitle(route)}</strong>
          </div>
          <div className="topbar-right">
            {mockMode && (
              <span className="demo-pill">
                <span /> DEMO MODE
              </span>
            )}
            <button
              className="icon-button top-search"
              onClick={() => {
                navigate("sessions");
                document.getElementById("history-search")?.focus();
              }}
              aria-label="Search sessions"
            >
              <Icon name="search" />
            </button>
            <button
              className="top-avatar"
              onClick={() => navigate("settings")}
              aria-label="Open profile"
            >
              {user?.name
                ?.split(" ")
                .map((p) => p[0])
                .join("") ?? "AM"}
            </button>
          </div>
        </header>
        <div className="page-content">
          {error && (
            <div className="alert-error">
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss">
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {route === "overview" && (
            <Overview
              user={user}
              sessions={sessions}
              patterns={patterns}
              onStart={() => setModal(true)}
              onNavigate={navigate}
              onOpen={(id) => {
                setActiveSession(id);
                navigate("analysis");
              }}
            />
          )}
          {route === "sessions" && (
            <Sessions
              sessions={filtered}
              query={query}
              setQuery={setQuery}
              onStart={() => setModal(true)}
              onOpen={(session) => {
                setActiveSession(session.id);
                navigate(
                  session.status === "in_progress" ? "chat" : "analysis",
                );
              }}
              canDelete={mockMode}
              onDelete={async (id) => {
                try {
                  await api.deleteSession(id);
                  setSessions(await api.sessions());
                  notify("Session deleted.");
                } catch (e) {
                  setError(
                    e instanceof Error
                      ? e.message
                      : "Session deletion is unavailable.",
                  );
                }
              }}
            />
          )}
          {route === "chat" && (
            <Chat
              session={current}
              busy={busy}
              realMode={!mockMode}
              onSend={submitMessage}
              onComplete={completeSession}
            />
          )}
          {route === "analysis" && (
            <AnalysisPage
              analysis={analysis}
              session={current}
              canFeedback={mockMode}
              onFeedback={sendFeedback}
              onNavigate={navigate}
            />
          )}
          {route === "patterns" && (
            <PatternsPage
              patterns={patterns}
              realMode={!mockMode}
              canFeedback={mockMode}
              onFeedback={sendFeedback}
            />
          )}
          {route === "recommendations" && (
            <Recommendations
              items={recommendations}
              realMode={!mockMode}
              onFeedback={sendFeedback}
            />
          )}
          {route === "settings" && (
            <Settings
              user={user}
              consent={consent}
              mockMode={mockMode}
              onConsent={(value) => {
                setConsent(value);
                localStorage.setItem("cognitrace.demo.consent", String(value));
                notify(
                  value ? "Session saving enabled." : "Session saving paused.",
                );
              }}
              onDeleteAll={async () => {
                for (const session of sessions)
                  await api.deleteSession(session.id);
                setSessions([]);
                notify("Your demo session data has been deleted.");
              }}
              onSignOut={() => {
                clearAuth();
                setUser(null);
                navigate("auth");
              }}
            />
          )}
        </div>
      </main>
      {modal && (
        <NewSessionModal
          busy={busy}
          realMode={!mockMode}
          onClose={() => setModal(false)}
          onStart={startSession}
        />
      )}
      {toast && (
        <div className="toast">
          <span className="toast-check">
            <Icon name="check" size={15} />
          </span>
          {toast}
        </div>
      )}
    </div>
  );
}
function routeTitle(route: Route) {
  return {
    overview: "Overview",
    sessions: "My sessions",
    analysis: "Reflections",
    patterns: "Patterns",
    recommendations: "For you",
    settings: "Settings",
    chat: "New session",
    auth: "Sign in",
  }[route];
}
function PageHeading({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow: string;
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
      {action}
    </div>
  );
}
function Overview({
  user,
  sessions,
  patterns,
  onStart,
  onNavigate,
  onOpen,
}: {
  user: User | null;
  sessions: Session[];
  patterns: Pattern[];
  onStart: () => void;
  onNavigate: (r: Route) => void;
  onOpen: (id: string) => void;
}) {
  const completed = sessions.filter((s) => s.status === "completed");
  return (
    <>
      <PageHeading
        eyebrow="THURSDAY, OCTOBER 22"
        title={`Good morning${user?.name ? `, ${user.name.split(" ")[0]}` : ""}.`}
        text="A little space to think things through, one decision at a time."
        action={
          <button className="button button-primary" onClick={onStart}>
            <Icon name="plus" size={16} /> Start a session
          </button>
        }
      />
      <section className="welcome-banner">
        <div className="welcome-copy">
          <span className="banner-kicker">
            <Icon name="spark" size={15} /> YOUR THINKING, IN VIEW
          </span>
          <h2>
            Make room for a<br />
            clearer next step.
          </h2>
          <p>
            Work through a decision, untangle a challenge, or simply reflect on
            what’s on your mind.
          </p>
          <button className="button button-light" onClick={onStart}>
            Begin a reflection <Icon name="arrow" size={15} />
          </button>
        </div>
        <div className="banner-visual" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <div className="visual-core">
            <Icon name="spark" size={27} />
          </div>
          <span className="orbit-point point-one" />
          <span className="orbit-point point-two" />
          <span className="orbit-point point-three" />
        </div>
        <div className="banner-footnote">A PRIVATE SPACE TO THINK</div>
      </section>
      <section className="stats-grid">
        <Stat
          icon="sessions"
          label="Sessions completed"
          value={String(completed.length).padStart(2, "0")}
          note="Your reflections so far"
        />
        <Stat
          icon="patterns"
          label="Possible patterns"
          value={String(patterns.length).padStart(2, "0")}
          note="Based on session evidence"
        />
        <Stat
          icon="trend"
          label="Thinking time"
          value={`${completed.reduce((sum, s) => sum + (parseInt(s.duration) || 0), 0)}m`}
          note="Time spent reflecting"
        />
      </section>
      <div className="section-heading">
        <div>
          <h2>Recent reflections</h2>
          <p>Your recent thinking, ready when you are.</p>
        </div>
        <button className="text-link" onClick={() => onNavigate("sessions")}>
          View all sessions <Icon name="arrow" size={14} />
        </button>
      </div>
      {sessions.length ? (
        <div className="reflection-list">
          {sessions.slice(0, 3).map((session, i) => (
            <button
              className="reflection-row"
              key={session.id}
              onClick={() => onOpen(session.id)}
            >
              <span className={`reflection-icon icon-tone-${i % 3}`}>
                <Icon
                  name={
                    i === 0 ? "spark" : i === 1 ? "analysis" : "recommendations"
                  }
                  size={17}
                />
              </span>
              <span className="reflection-meta">
                <strong>{session.title}</strong>
                <small>
                  {session.topic} <span>·</span> {session.date}
                </small>
              </span>
              <span className={`status ${session.status}`}>
                {session.status === "completed" ? "Completed" : "In progress"}
              </span>
              <Icon name="chevron" size={17} />
            </button>
          ))}
        </div>
      ) : (
        <EmptyState
          title="Your first reflection starts here"
          text="Start a session to work through a decision or challenge."
          action={onStart}
        />
      )}
      <div className="gentle-note">
        <span className="note-spark">
          <Icon name="spark" size={16} />
        </span>
        <p>
          <strong>A gentle reminder</strong> These reflections are prompts for
          your own thinking. Patterns are possibilities to consider, not
          conclusions about you.
        </p>
        <button onClick={() => onNavigate("patterns")}>
          How patterns work <Icon name="arrow" size={13} />
        </button>
      </div>
    </>
  );
}
function Stat({
  icon,
  label,
  value,
  note,
}: {
  icon: string;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="stat-card">
      <span className="stat-icon">
        <Icon name={icon} />
      </span>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      <small>{note}</small>
    </div>
  );
}
function EmptyState({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: () => void;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name="spark" size={20} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action && (
        <button className="button button-secondary" onClick={action}>
          Get started
        </button>
      )}
    </div>
  );
}
function Sessions({
  sessions,
  query,
  setQuery,
  onStart,
  onOpen,
  onDelete,
  canDelete,
}: {
  sessions: Session[];
  query: string;
  setQuery: (q: string) => void;
  onStart: () => void;
  onOpen: (s: Session) => void;
  onDelete: (id: string) => void;
  canDelete: boolean;
}) {
  const [removeId, setRemoveId] = useState("");
  return (
    <>
      <PageHeading
        eyebrow="YOUR SPACE"
        title="My sessions"
        text="A record of the questions you’ve taken time to think through."
        action={
          <button className="button button-primary" onClick={onStart}>
            <Icon name="plus" size={16} /> New session
          </button>
        }
      />
      <div className="toolbar">
        <label className="search-box">
          <Icon name="search" size={17} />
          <input
            id="history-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search your sessions"
          />
          <kbd>Ctrl K</kbd>
        </label>
        <span className="result-count">
          {sessions.length} {sessions.length === 1 ? "session" : "sessions"}
        </span>
      </div>
      <div className="history-list">
        {sessions.map((session) => (
          <article className="history-card" key={session.id}>
            <button className="history-main" onClick={() => onOpen(session)}>
              <span className="history-mark">
                <Icon
                  name={session.status === "completed" ? "analysis" : "clock"}
                  size={18}
                />
              </span>
              <span className="history-details">
                <strong>{session.title}</strong>
                <span>
                  {session.topic} <i>·</i> {session.duration}
                </span>
                <small>{session.date}</small>
              </span>
              <span className={"status " + session.status}>
                {session.status === "completed" ? "Completed" : "In progress"}
              </span>
              <Icon name="chevron" size={17} />
            </button>
            {canDelete && (
              <button
                className="delete-session"
                onClick={() => setRemoveId(session.id)}
                aria-label={"Delete " + session.title}
              >
                <Icon name="close" size={15} />
              </button>
            )}
          </article>
        ))}
        {sessions.length === 0 && (
          <EmptyState
            title={query ? "No sessions found" : "No sessions yet"}
            text={
              query
                ? "Try another search, or clear the search field."
                : "Your sessions will appear here when you start reflecting."
            }
            action={query ? undefined : onStart}
          />
        )}
      </div>
      {removeId && (
        <div className="modal-backdrop" onClick={() => setRemoveId("")}>
          <div
            className="dialog confirm-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="dialog-close" onClick={() => setRemoveId("")}>
              <Icon name="close" />
            </button>
            <div className="dialog-icon warning-icon">
              <Icon name="close" />
            </div>
            <h2>Delete this session?</h2>
            <p>
              This removes the session and its visible reflection data from your
              account.
            </p>
            <div className="dialog-actions">
              <button
                className="button button-secondary"
                onClick={() => setRemoveId("")}
              >
                Keep session
              </button>
              <button
                className="button button-danger"
                onClick={() => {
                  onDelete(removeId);
                  setRemoveId("");
                }}
              >
                Delete session
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function Chat({
  session,
  busy,
  realMode,
  onSend,
  onComplete,
}: {
  session?: Session;
  busy: boolean;
  realMode: boolean;
  onSend: (t: string) => void;
  onComplete: () => void;
}) {
  const [text, setText] = useState("");
  const bottomRef = useMemo(
    () => ({ current: null as HTMLDivElement | null }),
    [],
  );
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length, busy]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim() && !busy) {
      onSend(text);
      setText("");
    }
  };
  return (
    <>
      <div className="chat-heading">
        <button
          className="back-link"
          onClick={() => (location.hash = "/overview")}
        >
          ← &nbsp;Back to overview
        </button>
        <div className="chat-title-row">
          <div>
            <div className="eyebrow">REFLECTION SESSION</div>
            <h1>{session?.title ?? "New reflection"}</h1>
            <p>
              {realMode
                ? "Write your notes, then submit the completed transcript for extraction."
                : "Take a moment to think out loud."}
            </p>
          </div>
          <button
            onClick={onComplete}
            disabled={busy || !session?.messages.length}
            className="button button-secondary"
          >
            Complete session <Icon name="check" size={15} />
          </button>
        </div>
        <div className="consent-strip">
          <Icon name="lock" size={15} />
          <span>
            {realMode
              ? "Draft notes stay in this tab until you submit the completed transcript."
              : "Demo conversation · Your thoughts are saved to demo history."}
          </span>
          <span className="consent-enabled">
            <i /> {session?.status === "in_progress" ? "In progress" : "Saved"}
          </span>
        </div>
      </div>
      <div className="chat-card">
        <div className="chat-messages">
          {session?.messages.length ? (
            session.messages.map((message, index) => (
              <MessageBubble key={message.id} message={message} index={index} />
            ))
          ) : (
            <div className="chat-empty">
              <span className="chat-orb">
                <Icon name="spark" size={22} />
              </span>
              <h2>What’s on your mind?</h2>
              <p>
                Start wherever you are. You can share a decision, a challenge,
                or a thought you’d like to unpack.
              </p>
              <div className="prompt-chips">
                {[
                  "I’m weighing two options…",
                  "I feel stuck on…",
                  "Help me think through…",
                ].map((item) => (
                  <button key={item} onClick={() => setText(item)}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}
          {busy && !realMode && (
            <div className="typing-row">
              <span className="assistant-avatar">
                <Icon name="spark" size={14} />
              </span>
              <span className="typing-dots">
                <i />
                <i />
                <i />
              </span>
              <small>Finding a helpful question…</small>
            </div>
          )}
          <div ref={(el) => (bottomRef.current = el)} />
        </div>
        <form className="composer" onSubmit={submit}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Share what you’re thinking…"
            rows={2}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(e);
              }
            }}
          />
          <div className="composer-foot">
            <span>
              Press <kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for a
              new line
            </span>
            <button
              className="send-button"
              disabled={busy || !text.trim()}
              aria-label="Add note"
            >
              <Icon name="send" size={17} />
            </button>
          </div>
        </form>
      </div>
      <p className="chat-disclaimer">
        <Icon name="lock" size={13} />
        {realMode
          ? "Gemini replies as you think. Complete the session to save its transcript and generate a reflection."
          : "Your demo reflections are stored in this browser."}
      </p>
    </>
  );
}
function MessageBubble({
  message,
  index,
}: {
  message: Message;
  index: number;
}) {
  const assistant = message.role === "assistant";
  return (
    <div className={`message-row ${assistant ? "assistant-row" : "user-row"}`}>
      <div className="message-avatar">
        {assistant ? <Icon name="spark" size={14} /> : "A"}
      </div>
      <div className="message-content">
        <div className="message-byline">
          {assistant ? "Cognitrace" : "You"} <span>{message.createdAt}</span>
        </div>
        <div
          className={`bubble ${assistant ? "assistant-bubble" : "user-bubble"}`}
        >
          {message.content}
        </div>
      </div>
    </div>
  );
}
function AnalysisPage({
  analysis,
  session,
  onFeedback,
  onNavigate,
  canFeedback,
}: {
  analysis: Analysis | null;
  session?: Session;
  onFeedback: (id: string, v: "helpful" | "not_helpful") => void;
  onNavigate: (r: Route) => void;
  canFeedback: boolean;
}) {
  const [vote, setVote] = useState("");
  const open = (v: "helpful" | "not_helpful") => {
    setVote(v);
    onFeedback(session?.id ?? "analysis", v);
  };
  return (
    <>
      <PageHeading
        eyebrow="A CLOSER LOOK"
        title="Session reflection"
        text="A recap to help you see the choices and questions that came up."
        action={
          <button
            className="button button-secondary"
            onClick={() => onNavigate("sessions")}
          >
            All sessions <Icon name="arrow" size={14} />
          </button>
        }
      />
      <div className="analysis-session-strip">
        <span className="analysis-session-icon">
          <Icon name="analysis" />
        </span>
        <span>
          <strong>{session?.title ?? "Choosing a project direction"}</strong>
          <small>
            {session?.topic ?? "Product decisions"} <i>·</i>{" "}
            {session?.date ?? "Today · 10:24 AM"}
          </small>
        </span>
        <span className="status completed">Completed</span>
      </div>
      {mockMode && (
        <div className="demo-disclaimer">
          <span>
            <Icon name="spark" size={15} />
          </span>
          <p>
            <strong>Example reflection</strong> This is demo content to show how
            a session summary could look. It isn’t a real AI analysis.
          </p>
        </div>
      )}
      {analysis ? (
        <>
          <section className="analysis-card">
            <div className="card-eyebrow">
              <span className="tiny-dot" /> SESSION SUMMARY
            </div>
            <p className="analysis-summary">{analysis.summary}</p>
            <div className="analysis-card-foot">
              <span>
                <Icon name="clock" size={14} /> Generated after session
              </span>
              <span>Based on this conversation</span>
            </div>
          </section>
          <div className="section-heading trace-heading">
            <div>
              <div className="eyebrow">WHAT CAME UP</div>
              <h2>Key moments</h2>
              <p>Grounded in what you shared during this session.</p>
            </div>
          </div>
          <div className="trace-list">
            {analysis.traces.map((trace, i) => (
              <article key={i} className="trace-card">
                <span className="trace-number">0{i + 1}</span>
                <div>
                  <span className="trace-type">{trace.type}</span>
                  <p>{trace.content}</p>
                  <div className="evidence-chip">
                    <Icon name="sessions" size={13} />
                    {trace.evidence}
                  </div>
                </div>
              </article>
            ))}
          </div>
          <section className="reflection-prompt">
            <span className="prompt-spark">
              <Icon name="spark" />
            </span>
            <div>
              <div className="eyebrow">A QUESTION TO CARRY FORWARD</div>
              <p>{analysis.reflection}</p>
            </div>
          </section>
          {canFeedback && (
            <div className="feedback-panel">
              <span>Did this reflection feel useful?</span>
              <div>
                <button
                  className={vote === "helpful" ? "vote-selected" : ""}
                  onClick={() => open("helpful")}
                >
                  ↗ &nbsp;Yes, helpful
                </button>
                <button
                  className={vote === "not_helpful" ? "vote-selected" : ""}
                  onClick={() => open("not_helpful")}
                >
                  Not quite
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <EmptyState
          title="No reflection available yet"
          text="Complete a session to see a reflection here."
          action={() => onNavigate("chat")}
        />
      )}
    </>
  );
}
function PatternsPage({
  patterns,
  onFeedback,
  realMode,
  canFeedback,
}: {
  patterns: Pattern[];
  onFeedback: (id: string, v: "helpful" | "not_helpful") => void;
  realMode: boolean;
  canFeedback: boolean;
}) {
  const [expanded, setExpanded] = useState("p1");
  const [votes, setVotes] = useState<Record<string, string>>({});
  return (
    <>
      <PageHeading
        eyebrow="OVER TIME"
        title="Possible patterns"
        text="Tentative themes across your sessions, with the evidence to explore for yourself."
      />
      <div className="pattern-notice">
        <span className="notice-icon">
          <Icon name="spark" size={16} />
        </span>
        <p>
          <strong>These are possibilities, not conclusions.</strong> Each theme
          is connected to the sessions that informed it. You can disagree,
          dismiss, or simply leave it as a question.
        </p>
      </div>
      {patterns.length ? (
        <div className="pattern-list">
          {patterns.map((item, i) => (
            <article
              className={
                "pattern-card " +
                (expanded === item.id ? "pattern-expanded" : "")
              }
              key={item.id}
            >
              <button
                className="pattern-main"
                onClick={() => setExpanded(expanded === item.id ? "" : item.id)}
              >
                <span className={"pattern-symbol pattern-symbol-" + (i % 3)}>
                  <Icon name={i ? "trend" : "patterns"} size={19} />
                </span>
                <span className="pattern-title-block">
                  <span className="pattern-tag">POSSIBLE THEME</span>
                  <strong>{item.title}</strong>
                  <small>
                    {item.sessions} sessions · tentative observation
                  </small>
                </span>
                {item.confidence !== undefined && (
                  <span className="confidence-wrap">
                    <span className="confidence-label">
                      SIGNAL STRENGTH{" "}
                      <b>{Math.round(item.confidence * 100)}%</b>
                    </span>
                    <span className="confidence-track">
                      <i style={{ width: item.confidence * 100 + "%" }} />
                    </span>
                  </span>
                )}
                <Icon name="chevron" size={18} />
              </button>
              {expanded === item.id && (
                <div className="pattern-detail">
                  <p>{item.description}</p>
                  <h4>Sessions that informed this</h4>
                  <div className="evidence-tags">
                    {item.evidence.map((e) => (
                      <span key={e}>
                        <Icon name="sessions" size={13} />
                        {e}
                      </span>
                    ))}
                  </div>
                  {canFeedback && (
                    <div className="pattern-actions">
                      <span>Does this resonate with you?</span>
                      <button
                        className={
                          votes[item.id] === "helpful" ? "vote-selected" : ""
                        }
                        onClick={() => {
                          setVotes({ ...votes, [item.id]: "helpful" });
                          onFeedback(item.id, "helpful");
                        }}
                      >
                        Yes
                      </button>
                      <button
                        className={
                          votes[item.id] === "not_helpful"
                            ? "vote-selected"
                            : ""
                        }
                        onClick={() => {
                          setVotes({ ...votes, [item.id]: "not_helpful" });
                          onFeedback(item.id, "not_helpful");
                        }}
                      >
                        Not really
                      </button>
                    </div>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title={
            realMode
              ? "No pattern history endpoint yet"
              : "More sessions, more context"
          }
          text={
            realMode
              ? "The backend returns patterns with a newly analyzed transcript. It does not yet provide a route to reload pattern history."
              : "Possible themes may appear after a few completed sessions. One conversation is never enough to call a pattern."
          }
        />
      )}
      <div className="pattern-footnote">
        <Icon name="lock" size={14} /> Patterns are generated from completed
        sessions only. They are not diagnoses or personality labels.
      </div>
    </>
  );
}
function Recommendations({
  items,
  onFeedback,
  realMode,
}: {
  items: string[];
  onFeedback: (id: string, v: "helpful" | "not_helpful") => void;
  realMode: boolean;
}) {
  const [done, setDone] = useState<string[]>([]);
  const [vote, setVote] = useState("");
  return (
    <>
      <PageHeading
        eyebrow="SMALL STEPS, YOURS TO TAKE"
        title="For your next step"
        text="Practical prompts inspired by your reflections. Take what feels useful and leave the rest."
      />
      <div className="recommend-intro">
        <span className="rec-orbit">
          <Icon name="spark" size={23} />
        </span>
        <div>
          <span className="eyebrow">A FEW IDEAS TO TRY</span>
          <p>
            These are invitations, not instructions. You decide what fits your
            situation.
          </p>
        </div>
      </div>
      {realMode && items.length === 0 ? (
        <EmptyState
          title="Recommendations are not connected yet"
          text="The backend does not currently provide a recommendations endpoint."
        />
      ) : (
        <div className="recommend-list">
          {items.map((item, i) => (
            <article
              className={
                "recommend-card " +
                (done.includes(item) ? "recommend-done" : "")
              }
              key={item}
            >
              <span className="recommend-index">0{i + 1}</span>
              <div className="recommend-copy">
                <span className="recommend-kind">
                  {
                    [
                      "A QUICK CHECK-IN",
                      "A SMALL EXPERIMENT",
                      "A NOTE FOR LATER",
                    ][i % 3]
                  }
                </span>
                <p>{item}</p>
                <small>
                  <Icon name="clock" size={13} />{" "}
                  {i === 0
                    ? "5 minutes"
                    : i === 1
                      ? "15 minutes"
                      : "When it feels right"}
                </small>
              </div>
              <button
                className={
                  "recommend-check " + (done.includes(item) ? "checked" : "")
                }
                onClick={() =>
                  setDone(
                    done.includes(item)
                      ? done.filter((x) => x !== item)
                      : [...done, item],
                  )
                }
                aria-label="Mark as tried"
              >
                <Icon name="check" size={16} />
              </button>
            </article>
          ))}
        </div>
      )}
      {!realMode && (
        <div className="feedback-panel rec-feedback">
          <span>Are these ideas useful to you?</span>
          <div>
            <button
              className={vote === "helpful" ? "vote-selected" : ""}
              onClick={() => {
                setVote("helpful");
                onFeedback("recommendations", "helpful");
              }}
            >
              Yes, thanks
            </button>
            <button
              className={vote === "not_helpful" ? "vote-selected" : ""}
              onClick={() => {
                setVote("not_helpful");
                onFeedback("recommendations", "not_helpful");
              }}
            >
              Not for me
            </button>
          </div>
        </div>
      )}
    </>
  );
}
function Settings({
  user,
  consent,
  onConsent,
  onDeleteAll,
  onSignOut,
  mockMode,
}: {
  user: User | null;
  consent: boolean;
  onConsent: (v: boolean) => void;
  onDeleteAll: () => void;
  onSignOut: () => void;
  mockMode: boolean;
}) {
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <PageHeading
        eyebrow="YOUR ACCOUNT"
        title="Settings & privacy"
        text="You’re in control of what you share and what stays in your history."
      />
      <section className="settings-card">
        <div className="settings-card-heading">
          <span className="settings-icon">
            <Icon name="sessions" />
          </span>
          <div>
            <h2>Profile</h2>
            <p>Your account information.</p>
          </div>
        </div>
        <div className="setting-row">
          <span>
            <strong>Name</strong>
            <small>{user?.name ?? "Cognitrace user"}</small>
          </span>
          <span className="setting-value">Personal workspace</span>
        </div>
        <div className="setting-row">
          <span>
            <strong>Email</strong>
            <small>{user?.email ?? ""}</small>
          </span>
          <span className="setting-value">Account</span>
        </div>
        <div className="setting-row">
          <span>
            <strong>Sign out</strong>
            <small>Return to the sign in screen on this device.</small>
          </span>
          <button className="button button-secondary" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </section>
      <section className="settings-card">
        <div className="settings-card-heading">
          <span className="settings-icon">
            <Icon name="lock" />
          </span>
          <div>
            <h2>Your data, your choice</h2>
            <p>
              {mockMode
                ? "Choose whether demo conversations are kept in browser history."
                : "Submitted transcripts are saved to your account. The backend does not yet provide a delete or retention-preference route."}
            </p>
          </div>
        </div>
        <div className="setting-row consent-row">
          <span>
            <strong>Save sessions for reflection</strong>
            <small>
              Sessions are used to show your history and, when available,
              reflect across conversations.
            </small>
          </span>
          <button
            disabled={!mockMode}
            className={"toggle " + (consent ? "toggle-on" : "")}
            onClick={() => onConsent(!consent)}
            aria-pressed={consent}
          >
            <i />
          </button>
        </div>
        <div className="privacy-explainer">
          <Icon name="lock" size={15} />
          <p>
            {mockMode
              ? "Only share what you’re comfortable reflecting on. You can remove individual sessions or clear demo history below."
              : "Only submit information you are comfortable storing. Session deletion is not yet available through the backend."}
          </p>
        </div>
      </section>
      {mockMode && (
        <section className="settings-card danger-zone">
          <div className="settings-card-heading">
            <span className="settings-icon danger-settings">
              <Icon name="close" />
            </span>
            <div>
              <h2>Delete your data</h2>
              <p>Remove all session history from this demo workspace.</p>
            </div>
          </div>
          <div className="setting-row">
            <span>
              <strong>Clear session history</strong>
              <small>
                This permanently removes all saved demo sessions from this
                browser.
              </small>
            </span>
            <button
              className="button button-danger-outline"
              onClick={() => setConfirm(true)}
            >
              Delete all sessions
            </button>
          </div>
        </section>
      )}
      {confirm && (
        <div className="modal-backdrop" onClick={() => setConfirm(false)}>
          <div
            className="dialog confirm-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="dialog-close" onClick={() => setConfirm(false)}>
              <Icon name="close" />
            </button>
            <div className="dialog-icon warning-icon">
              <Icon name="close" />
            </div>
            <h2>Clear all session history?</h2>
            <p>This will remove every session saved in this demo workspace.</p>
            <div className="dialog-actions">
              <button
                className="button button-secondary"
                onClick={() => setConfirm(false)}
              >
                Cancel
              </button>
              <button
                className="button button-danger"
                onClick={() => {
                  onDeleteAll();
                  setConfirm(false);
                }}
              >
                Delete everything
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function NewSessionModal({
  busy,
  realMode,
  onClose,
  onStart,
}: {
  busy: boolean;
  realMode: boolean;
  onClose: () => void;
  onStart: (title: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("Decision");
  const prompts = [
    "Decision",
    "Work challenge",
    "Personal project",
    "Something else",
  ];
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="dialog new-session-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="dialog-close" onClick={onClose} aria-label="Close">
          <Icon name="close" />
        </button>
        <span className="dialog-eyebrow">
          <Icon name="spark" size={14} /> MAKE A LITTLE SPACE
        </span>
        <h2>What would you like to think through?</h2>
        <p>
          Give this reflection a name. You can start with a question, a
          decision, or whatever’s on your mind.
        </p>
        <label className="field-label" htmlFor="session-title">
          SESSION NAME
        </label>
        <input
          autoFocus
          id="session-title"
          className="session-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Choosing what to focus on"
          onKeyDown={(e) => {
            if (e.key === "Enter" && title.trim()) onStart(title.trim());
          }}
        />
        <label className="field-label">A STARTING POINT</label>
        <div className="topic-chips">
          {prompts.map((item) => (
            <button
              className={topic === item ? "topic-selected" : ""}
              onClick={() => setTopic(item)}
              key={item}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="dialog-privacy">
          <Icon name="lock" size={14} />
          {realMode
            ? "Your draft stays in this tab until you submit it. Submitted sessions are saved to your account."
            : "Your demo session is stored in this browser and can be deleted anytime."}
        </div>
        <div className="dialog-actions">
          <button className="button button-secondary" onClick={onClose}>
            Maybe later
          </button>
          <button
            disabled={!title.trim() || busy}
            className="button button-primary"
            onClick={() => onStart(title.trim())}
          >
            {busy ? "Starting…" : "Start reflecting"}{" "}
            <Icon name="arrow" size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

function AuthPage({
  busy,
  error,
  onSubmit,
}: {
  busy: boolean;
  error: string;
  onSubmit: (email: string, password: string, name?: string) => void;
}) {
  const [register, setRegister] = useState(false),
    [name, setName] = useState(""),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(email, password, register ? name : undefined);
  };
  return (
    <div className="auth-page">
      <div className="auth-side">
        <a className="brand auth-brand" href="#/auth">
          <span className="brand-mark">
            <Icon name="spark" size={19} />
          </span>
          <span className="brand-name">
            cognitrace<span className="brand-dot">.</span>
            <small>YOUR THINKING, IN VIEW</small>
          </span>
        </a>
        <div className="auth-side-content">
          <span className="banner-kicker">
            <Icon name="spark" size={15} /> A SPACE TO THINK CLEARLY
          </span>
          <h1>
            Every good decision
            <br />
            starts with a pause.
          </h1>
          <p>
            Work through a challenge, notice what matters, and find your next
            step with a little more clarity.
          </p>
          <div className="auth-quote">
            <span>“</span>
            <p>
              A thoughtful space to reflect on how you solve problems — at your
              pace, on your terms.
            </p>
          </div>
        </div>
        <span className="auth-side-foot">
          PRIVATE BY DESIGN &nbsp;·&nbsp; BUILT FOR REFLECTION
        </span>
        <div className="auth-decoration">
          <i />
          <i />
          <i />
        </div>
      </div>
      <div className="auth-main">
        <div className="auth-mobile-brand">
          <span className="brand-mark">
            <Icon name="spark" size={19} />
          </span>
          <span className="brand-name">
            cognitrace<span className="brand-dot">.</span>
          </span>
        </div>
        <div className="auth-form-wrap">
          <span className="eyebrow">
            {register ? "CREATE YOUR ACCOUNT" : "WELCOME BACK"}
          </span>
          <h2>
            {register ? "Start with a little space." : "Good to have you back."}
          </h2>
          <p>
            {register
              ? "Create an account to keep your reflections together."
              : "Sign in to pick up where your thinking left off."}
          </p>
          {mockMode && (
            <div className="auth-demo-notice">
              <Icon name="spark" size={14} /> Demo mode — use any email and
              password to continue.
            </div>
          )}
          {error && <div className="auth-error">{error}</div>}
          <form className="auth-form" onSubmit={submit}>
            {register && (
              <label>
                Your name
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="How should we address you?"
                  autoComplete="name"
                />
              </label>
            )}
            <label>
              Email address
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoComplete={register ? "new-password" : "current-password"}
              />
            </label>
            <button
              className="button button-primary auth-submit"
              disabled={busy}
            >
              {busy ? "One moment…" : register ? "Create account" : "Sign in"}{" "}
              <Icon name="arrow" size={15} />
            </button>
          </form>
          <div className="auth-switch">
            {register ? "Already have an account?" : "New to Cognitrace?"}{" "}
            <button onClick={() => setRegister(!register)}>
              {register ? "Sign in" : "Create an account"}
            </button>
          </div>
          <div className="auth-privacy">
            <Icon name="lock" size={14} /> Your reflections are personal. You
            choose what to share.
          </div>
        </div>
        <span className="auth-footer">
          By continuing, you agree to keep your reflections yours.
        </span>
      </div>
    </div>
  );
}
