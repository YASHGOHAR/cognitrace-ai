import { describe, expect, it, vi } from "vitest";
import { createBackendAdapter, toAnalysis, type ChatMessage, type Reasoning } from "./backendAdapter";
import { formatUserTranscript } from "./transcript";
import { appendChatTurn } from "./chatSession";
import type { Message } from "../types";

const reasoning: Reasoning = {
  problem: { text: "Find shortest path", evidence: "find shortest path" },
  decisions: [{ text: "Use BFS", evidence: "I will use BFS" }],
  justifications: [],
  alternatives_considered: [],
  assumptions: [],
};

describe("backend API adapter", () => {
  it("posts a completed transcript using the real request schema and a bearer header", async () => {
    const workflow = {
      session_id: "session-1",
      reasoning,
      relevant_previous_sessions: [],
      detected_patterns: [],
      insufficient_evidence: true,
      previous_sessions_considered: 0,
    };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(workflow), { status: 200 }));
    const adapter = createBackendAdapter({
      baseUrl: "https://api.example/api/",
      getAccessToken: () => "in-memory-user-token",
      fetcher,
    });

    const result = await adapter.submitTranscript("I will use BFS.");

    expect(result.session_id).toBe("session-1");
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.example/api/sessions");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("omit");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer in-memory-user-token");
    expect(JSON.parse(String(init.body))).toEqual({ session_text: "I will use BFS." });
  });

  it("maps the actual paginated history response without calling unsupported routes", async () => {
    const page = {
      items: [{
        session_id: "saved-2",
        created_at: "2026-10-22T10:00:00+00:00",
        session_text: "I will use BFS.",
        reasoning,
      }],
      limit: 100,
      offset: 0,
    };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(page), { status: 200 }));
    const adapter = createBackendAdapter({ baseUrl: "https://api.example/api", getAccessToken: () => "user-token", fetcher });

    const sessions = await adapter.listSessions();

    expect(sessions).toHaveLength(1);
    expect(sessions[0].id).toBe("saved-2");
    expect(sessions[0].messages[0].content).toBe("I will use BFS.");
    expect(fetcher.mock.calls[0][0]).toBe("https://api.example/api/sessions?limit=100&offset=0");
  });

  it("loads every page of session history using the existing endpoint", async () => {
    const rows = Array.from({ length: 100 }, (_, index) => ({
      session_id: `saved-${index}`,
      created_at: "2026-10-22T10:00:00+00:00",
      session_text: "I will use BFS.",
      reasoning,
    }));
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: rows, limit: 100, offset: 0 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ ...rows[0], session_id: "saved-last" }], limit: 100, offset: 100 }), { status: 200 }));
    const adapter = createBackendAdapter({ baseUrl: "https://api.example/api", getAccessToken: () => "user-token", fetcher });

    const sessions = await adapter.listSessions();

    expect(sessions).toHaveLength(101);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example/api/sessions?limit=100&offset=0",
      "https://api.example/api/sessions?limit=100&offset=100",
    ]);
  });

  it("does not issue unauthenticated requests", async () => {
    const fetcher = vi.fn();
    const adapter = createBackendAdapter({ baseUrl: "https://api.example/api", getAccessToken: () => undefined, fetcher });

    await expect(adapter.listSessions()).rejects.toThrow("Please sign in");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("returns a safe error for unauthorized responses without echoing response bodies", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("private token or user text", { status: 401 }));
    const adapter = createBackendAdapter({ baseUrl: "https://api.example/api", getAccessToken: () => "token", fetcher });

    const error: unknown = await adapter.listSessions().then(
      () => undefined,
      (value: unknown) => value,
    );
    expect(error).toBeInstanceOf(Error);
    if (error instanceof Error) {
      expect(error.message).toBe("Your sign-in has expired. Please sign in again.");
      expect(error.message).not.toContain("private token");
    }
  });

  it("requests a Gemini chat reply with the authenticated conversation", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ message: "Keep going." }), { status: 200 }));
    const adapter = createBackendAdapter({
      baseUrl: "http://localhost:8000/api",
      getAccessToken: () => "token",
      fetcher,
    });

    await expect(adapter.chat([{ role: "user", content: "I am stuck." }])).resolves.toBe("Keep going.");
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/sessions/chat");
    expect(JSON.parse(String(init.body))).toEqual({
      messages: [{ role: "user", content: "I am stuck." }],
    });
  });

  it("maps validated evidence into a reflection view without inventing quotes", () => {
    const view = toAnalysis(reasoning);
    expect(view.traces).toEqual([
      { type: "Problem", content: "Find shortest path", evidence: "find shortest path" },
      { type: "Decision", content: "Use BFS", evidence: "I will use BFS" },
    ]);
  });

  it("builds saved evidence from the user's words only", () => {
    expect(formatUserTranscript([
      { role: "user", content: "  I prefer option A.  " },
      { role: "assistant", content: "Option A sounds reasonable." },
      { role: "user", content: "I will decide after asking the team." },
      { role: "assistant", content: "That may give you useful evidence." },
    ])).toBe("I prefer option A.\n\nI will decide after asking the team.");
  });

  it("removes a user turn after a failed chat request so retries do not duplicate it", async () => {
    const messages: Message[] = [];
    const requestReply = vi.fn().mockRejectedValue(new Error("offline"));

    await expect(appendChatTurn(messages, "I am stuck.", requestReply)).rejects.toThrow("offline");

    expect(messages).toEqual([]);
    expect(requestReply).toHaveBeenCalledOnce();
  });

  it("keeps a successful user/assistant exchange in the draft", async () => {
    const messages: Message[] = [];

    const result = await appendChatTurn(messages, "I am stuck.", async () => "What feels hardest?");

    expect(result.map(({ role, content }) => ({ role, content }))).toEqual([
      { role: "user", content: "I am stuck." },
      { role: "assistant", content: "What feels hardest?" },
    ]);
  });
});
