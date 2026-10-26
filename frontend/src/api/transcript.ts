import type { Message } from "../types";

/** Keep reflection evidence grounded in the user's words, not generated replies. */
export function formatUserTranscript(messages: Pick<Message, "role" | "content">[]): string {
  return messages
    .filter((message) => message.role === "user")
    .map((message) => message.content.trim())
    .filter(Boolean)
    .join("\n\n");
}
