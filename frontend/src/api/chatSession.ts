import type { Message } from "../types";
import type { ChatMessage } from "./backendAdapter";

/** Append a user turn, request its reply, and roll it back if the request fails. */
export async function appendChatTurn(
  messages: Message[],
  content: string,
  requestReply: (conversation: ChatMessage[]) => Promise<string>,
): Promise<Message[]> {
  const userMessage: Message = {
    id: crypto.randomUUID(),
    role: "user",
    content,
    createdAt: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
  };
  messages.push(userMessage);

  try {
    const reply = await requestReply(
      messages.map(({ role, content: message }) => ({ role, content: message })),
    );
    messages.push({
      id: crypto.randomUUID(),
      role: "assistant",
      content: reply,
      createdAt: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
    });
    return [...messages];
  } catch (error) {
    const failedTurn = messages.findIndex((message) => message.id === userMessage.id);
    if (failedTurn >= 0) messages.splice(failedTurn, 1);
    throw error;
  }
}
