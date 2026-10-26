import { createClient, type User as SupabaseUser } from "@supabase/supabase-js";
import type { Analysis, Message, Pattern, Session, User } from "../types";
import {
  createBackendAdapter,
  toAnalysis,
  toPatterns,
  toSession,
  type WorkflowResponse,
} from "./backendAdapter";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "https://cognitrace-ai.onrender.com/api";
export const mockMode = import.meta.env.VITE_USE_MOCK_API !== "false";
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
const supabase = supabaseUrl && supabasePublishableKey
  ? createClient(supabaseUrl, supabasePublishableKey, {
      auth: {
        autoRefreshToken: true,
        persistSession: false,
        detectSessionInUrl: false,
      },
    })
  : undefined;

let accessToken: string | undefined;
let currentUser: User | undefined;
const drafts = new Map<string, Session>();
const completedAnalysis = new Map<string, Analysis>();
let recentPatterns: Pattern[] = [];

export const clearAuth = () => {
  accessToken = undefined;
  currentUser = undefined;
  drafts.clear();
  completedAnalysis.clear();
  recentPatterns = [];
  if (!mockMode && supabase) void supabase.auth.signOut();
};

const backend = createBackendAdapter({
  baseUrl,
  getAccessToken: () => accessToken,
});

if (supabase) {
  supabase.auth.onAuthStateChange((_event, session) => {
    accessToken = session?.access_token;
    currentUser = session?.user ? toUser(session.user) : undefined;
  });
}

const key = "cognitrace.demo.sessions";
const seedSessions: Session[] = [
  { id: "s-101", title: "Choosing a project direction", topic: "Product decisions", date: "Today · 10:24 AM", status: "completed", duration: "18 min", messages: [{ id: "m1", role: "user", content: "I’m deciding between polishing the current prototype and starting a more ambitious version. The deadline is three weeks away.", createdAt: "10:24 AM" }, { id: "m2", role: "assistant", content: "What would make the current prototype feel ready enough to share? It may help to separate the smallest useful improvement from the bigger idea.", createdAt: "10:24 AM" }, { id: "m3", role: "user", content: "The core flow works. I keep thinking a new version would avoid some compromises, but I have not asked anyone to try the existing one.", createdAt: "10:27 AM" }, { id: "m4", role: "assistant", content: "You have two open questions: what users need next, and what the new version would truly unlock. A small test of the current flow could give you evidence for both.", createdAt: "10:28 AM" }] },
  { id: "s-102", title: "Planning a difficult conversation", topic: "Communication", date: "Yesterday · 4:12 PM", status: "completed", duration: "12 min", messages: [] },
  { id: "s-103", title: "Organizing a busy week", topic: "Planning", date: "Oct 19 · 9:05 AM", status: "completed", duration: "9 min", messages: [] },
  { id: "s-104", title: "Learning a new framework", topic: "Learning", date: "Oct 17 · 2:36 PM", status: "completed", duration: "15 min", messages: [] },
];
const demoWait = () => new Promise((resolve) => setTimeout(resolve, 120));
const readDemoSessions = (): Session[] => {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) as Session[] : seedSessions;
  } catch {
    return seedSessions;
  }
};
const persistDemoSessions = (value: Session[]) => localStorage.setItem(key, JSON.stringify(value));
const toUser = (user: SupabaseUser): User => ({
  id: user.id,
  name: String(user.user_metadata?.full_name ?? user.user_metadata?.name ?? user.email?.split("@")[0] ?? "Cognitrace user"),
  email: user.email ?? "",
});

function requireSupabase() {
  if (!supabase) throw new Error("Real sign-in is not configured. Add the Supabase URL and publishable key to your local environment.");
  return supabase;
}

export const api = {
  async me(): Promise<User> {
    if (mockMode) { await demoWait(); return { id: "u-demo", name: "Alex Morgan", email: "alex@example.com" }; }
    if (!currentUser || !accessToken) throw new Error("Please sign in to continue.");
    return currentUser;
  },
  async authenticate(email: string, password: string, name?: string): Promise<User> {
    if (mockMode) {
      await demoWait();
      return { id: "u-demo", name: name || email.split("@")[0], email };
    }
    const client = requireSupabase();
    const result = name
      ? await client.auth.signUp({ email, password, options: { data: { full_name: name } } })
      : await client.auth.signInWithPassword({ email, password });
    if (result.error) throw new Error("Sign-in could not be completed. Check your credentials or account confirmation settings.");
    if (!result.data.session || !result.data.user) throw new Error("Account created. Confirm your email, then sign in.");
    accessToken = result.data.session.access_token;
    currentUser = toUser(result.data.user);
    return currentUser;
  },
  async sessions(): Promise<Session[]> {
    if (mockMode) { await demoWait(); return readDemoSessions(); }
    return [...drafts.values(), ...await backend.listSessions()];
  },
  async createSession(topic: string): Promise<Session> {
    if (mockMode) {
      const session: Session = { id: crypto.randomUUID(), title: topic, topic: "Reflection", date: "Just now", status: "in_progress", duration: "New", messages: [] };
      persistDemoSessions([session, ...readDemoSessions()]);
      await demoWait();
      return session;
    }
    const session: Session = { id: crypto.randomUUID(), title: topic, topic: "Completed transcript", date: "Not saved yet", status: "in_progress", duration: "Draft", messages: [] };
    drafts.set(session.id, session);
    return session;
  },
  async sendMessage(sessionId: string, content: string): Promise<Message[]> {
    if (mockMode) {
      const current = readDemoSessions();
      const session = current.find((item) => item.id === sessionId);
      if (!session) throw new Error("This session could not be found.");
      const now = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      session.messages.push({ id: crypto.randomUUID(), role: "user", content, createdAt: now });
      await demoWait();
      session.messages.push({ id: crypto.randomUUID(), role: "assistant", content: "Thanks for laying that out. What feels like the most important constraint to keep in view as you consider your options?", createdAt: now });
      persistDemoSessions(current);
      return [...session.messages];
    }
    const draft = drafts.get(sessionId);
    if (!draft) throw new Error("Only an unsaved transcript can receive new notes.");
    draft.messages.push({ id: crypto.randomUUID(), role: "user", content, createdAt: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) });
    const reply = await backend.chat(
      draft.messages.map(({ role, content: message }) => ({ role, content: message })),
    );
    draft.messages.push({
      id: crypto.randomUUID(),
      role: "assistant",
      content: reply,
      createdAt: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
    });
    return [...draft.messages];
  },
  async completeSession(sessionId: string): Promise<string> {
    if (mockMode) {
      const current = readDemoSessions();
      const session = current.find((item) => item.id === sessionId);
      if (session) session.status = "completed";
      persistDemoSessions(current);
      await demoWait();
      return sessionId;
    }
    const draft = drafts.get(sessionId);
    if (!draft || !draft.messages.length) throw new Error("Add at least one note before submitting the transcript.");
    const transcript = draft.messages.map((message) => message.content).join("\n\n");
    const result: WorkflowResponse = await backend.submitTranscript(transcript);
    drafts.delete(sessionId);
    completedAnalysis.set(result.session_id, toAnalysis(result.reasoning, result.detected_patterns[0]?.reflection_question));
    recentPatterns = toPatterns(result);
    return result.session_id;
  },
  async deleteSession(id: string): Promise<void> {
    if (!mockMode) throw new Error("Session deletion is not available in the backend yet.");
    persistDemoSessions(readDemoSessions().filter((session) => session.id !== id));
    await demoWait();
  },
  async analysis(sessionId: string): Promise<Analysis> {
    if (mockMode) {
      await demoWait();
      return { summary: "You weighed a near-term test against a larger rebuild. Your reflection highlighted that the current flow has not yet been tried by users, leaving a useful source of evidence unexplored.", traces: [{ type: "Decision point", content: "Considered polishing the current prototype versus starting a new version.", evidence: "Choosing a project direction · 10:24 AM" }, { type: "Open question", content: "Whether user feedback would change the direction or scope of the work.", evidence: "Choosing a project direction · 10:27 AM" }], reflection: "What is the smallest test that could help you choose with more confidence?" };
    }
    const cached = completedAnalysis.get(sessionId);
    if (cached) return cached;
    const record = await backend.getSession(sessionId);
    return toAnalysis(record.reasoning);
  },
  async patterns(): Promise<Pattern[]> {
    if (mockMode) {
      await demoWait();
      return [{ id: "p1", title: "Testing assumptions with a small first step", description: "In several sessions, you explored a lightweight way to gather information before committing to a larger plan.", confidence: .72, sessions: 3, evidence: ["Choosing a project direction", "Organizing a busy week", "Learning a new framework"] }, { id: "p2", title: "Making trade-offs explicit", description: "You often compare options by naming the time, effort, or coordination each would require.", confidence: .64, sessions: 2, evidence: ["Choosing a project direction", "Planning a difficult conversation"] }];
    }
    return recentPatterns;
  },
  async recommendations(): Promise<string[]> {
    if (mockMode) { await demoWait(); return ["Before your next decision, write down one assumption you could check this week.", "Try a 15-minute “first test” before expanding the scope of a project.", "After a decision, note what evidence would make you revisit it."]; }
    return [];
  },
  async feedback(_targetId: string, _value: "helpful" | "not_helpful"): Promise<void> {
    if (mockMode) { await demoWait(); return; }
    throw new Error("Feedback is not available in the backend yet.");
  },
};

export { toAnalysis, toPatterns, toSession };
