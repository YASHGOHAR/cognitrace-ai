import { describe, expect, it, vi } from "vitest";
import { createBackendAdapter, toAnalysis, type Reasoning } from "./backendAdapter";

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
});
