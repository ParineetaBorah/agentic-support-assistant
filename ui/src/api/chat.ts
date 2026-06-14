import { API_BASE_URL, apiClient } from "./client";
import type { ChatRequest, ChatResponse, ConversationHistory, ConversationSummary } from "../types";

export async function sendMessage(message: string, conversationId?: string): Promise<ChatResponse> {
  const body: ChatRequest = { message, conversation_id: conversationId };
  const response = await apiClient.post<ChatResponse>("/chat", body);
  return response.data;
}

export interface ChatStreamHandlers {
  onStatus?: (status: string) => void;
  onToken?: (content: string) => void;
  onDone?: (response: ChatResponse) => void;
  onError?: (message: string) => void;
}

export async function streamMessage(
  message: string,
  conversationId: string | undefined,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const body: ChatRequest = { message, conversation_id: conversationId };
  const token = localStorage.getItem("acme_token");

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (response.status === 401) {
    localStorage.removeItem("acme_token");
    localStorage.removeItem("acme_user");
    window.location.href = "/login";
    throw new Error("API Error: 401");
  }

  if (!response.ok || !response.body) {
    throw new Error(`API Error: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventType = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice("event: ".length).trim();
      } else if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice("data: ".length));
        switch (eventType) {
          case "status":
            handlers.onStatus?.(data.status);
            break;
          case "token":
            handlers.onToken?.(data.content);
            break;
          case "done":
            handlers.onDone?.(data as ChatResponse);
            break;
          case "error":
            handlers.onError?.(data.message);
            break;
        }
        eventType = "";
      }
    }
  }
}

export async function getConversationHistory(conversationId: string): Promise<ConversationHistory> {
  const response = await apiClient.get<ConversationHistory>(`/conversations/${conversationId}`);
  return response.data;
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const response = await apiClient.get<ConversationSummary[]>("/conversations");
  return response.data;
}
