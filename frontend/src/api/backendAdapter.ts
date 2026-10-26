import type { Analysis, Pattern, Session } from "../types";

export type ReasoningItem = { text: string; evidence: string };
export type Reasoning = {
  problem: ReasoningItem | null;
  decisions: ReasoningItem[];
  justifications: ReasoningItem[];
  alternatives_considered: ReasoningItem[];
  assumptions: ReasoningItem[];
};
export type StoredSession = {
  session_id: string;
  created_at: string;
  session_text: string;
  reasoning: Reasoning;
};
export type WorkflowResponse = {
  session_id: string;
  reasoning: Reasoning;
  relevant_previous_sessions: Array<{
    session_id: string;
    timestamp: string;
    relevance_score: number;
    session_text: string;
    reasoning: Reasoning;
  }>;
  detected_patterns: Array<{
    description: string;
    category: string;
    supporting_session_ids: string[];
    supporting_evidence: Array<{
      session_id: string;
      category: string;
      text: string;
      evidence: string;
    }>;
    distinct_session_count: number;
    counterexamples: Array<{
      session_id: string;
      category: string;
      text: string;
      evidence: string;
    }>;
    reflection_question: string;
  }>;
  insufficient_evidence: boolean;
  previous_sessions_considered: number;
};
export type ChatMessage = { role: "user" | "assistant"; content: string };

type AdapterOptions = {
  baseUrl: string;
  getAccessToken: () => string | undefined;
  fetcher?: typeof fetch;
};

const requestError = (status: number) =>
  status === 401
    ? "Your sign-in has expired. Please sign in again."
    : status === 422
      ? "The session text was not accepted. Check it and try again."
      : status >= 500
        ? "The Cognitrace service could not process this request right now."
        : "The Cognitrace service rejected this request.";

export function toSession(record: StoredSession): Session {
  const title = record.session_text.split(/\r?\n/)[0].trim().slice(0, 64) || "Reasoning session";
  const date = new Date(record.created_at);
  return {
    id: record.session_id,
    title,
    topic: "Reasoning session",
    date: Number.isNaN(date.getTime()) ? record.created_at : date.toLocaleString(),
    status: "completed",
    duration: "—",
    messages: [{
      id: record.session_id + "-source",
      role: "user",
      content: record.session_text,
      createdAt: Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
    }],
  };
}

export function toAnalysis(reasoning: Reasoning, reflectionQuestion?: string): Analysis {
  const traces = [
    ...(reasoning.problem ? [{ type: "Problem", ...reasoning.problem }] : []),
    ...reasoning.decisions.map((item) => ({ type: "Decision", ...item })),
    ...reasoning.justifications.map((item) => ({ type: "Justification", ...item })),
    ...reasoning.alternatives_considered.map((item) => ({ type: "Alternative considered", ...item })),
    ...reasoning.assumptions.map((item) => ({ type: "Assumption", ...item })),
  ];
  return {
    summary: reasoning.problem?.text ?? "Reasoning statements extracted from the session are shown below.",
    traces: traces.map((item) => ({
      type: item.type,
      content: item.text,
      evidence: item.evidence,
    })),
    reflection: reflectionQuestion ?? "Which part of this reasoning might you revisit if new evidence appeared?",
  };
}

export function toPatterns(result: WorkflowResponse): Pattern[] {
  return result.detected_patterns.map((item, index) => ({
    id: item.category + "-" + index,
    title: item.description,
    description: item.description,
    evidence: item.supporting_evidence.map((evidence) => evidence.session_id + ": “" + evidence.evidence + "”"),
    sessions: item.distinct_session_count,
  }));
}

/** A deliberately small adapter for the backend's implemented session routes. */
export function createBackendAdapter({ baseUrl, getAccessToken, fetcher = fetch }: AdapterOptions) {
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = getAccessToken();
    if (!token) throw new Error("Please sign in before accessing your sessions.");
    let response: Response;
    try {
      response = await fetcher(baseUrl.replace(/\/$/, "") + path, {
        ...init,
        credentials: "omit",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: "Bearer " + token,
          ...init.headers,
        },
      });
    } catch {
      throw new Error("Could not reach the Cognitrace service. Check your connection and try again.");
    }
    if (!response.ok) throw new Error(requestError(response.status));
    return response.json() as Promise<T>;
  }

  return {
    async listSessions(): Promise<Session[]> {
      const page = await request<{ items: StoredSession[]; limit: number; offset: number }>("/sessions?limit=100&offset=0");
      return page.items.map(toSession);
    },
    async getSession(sessionId: string): Promise<StoredSession> {
      return request<StoredSession>("/sessions/" + encodeURIComponent(sessionId));
    },
    async submitTranscript(sessionText: string): Promise<WorkflowResponse> {
      return request<WorkflowResponse>("/sessions", {
        method: "POST",
        body: JSON.stringify({ session_text: sessionText }),
      });
    },
    async chat(messages: ChatMessage[]): Promise<string> {
      const result = await request<{ message: string }>("/sessions/chat", {
        method: "POST",
        body: JSON.stringify({ messages }),
      });
      return result.message;
    },
  };
}
