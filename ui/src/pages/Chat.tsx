import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getConversationHistory, listConversations, streamMessage } from "../api/chat";
import type { ConversationSummary, User } from "../types";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  toolsCalled?: string[];
  riskLevel?: string;
}

const RISK_LEVEL_PATTERN = /risk level:?\*{0,2}\s*\*{0,2}\s*(critical|high|medium|low)/i;

const RISK_BADGE_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};

function extractRiskLevel(text: string): string | undefined {
  return text.match(RISK_LEVEL_PATTERN)?.[1].toLowerCase();
}

function loadUser(): User | null {
  const stored = localStorage.getItem("acme_user");
  return stored ? (JSON.parse(stored) as User) : null;
}

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function Chat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [streamingStatus, setStreamingStatus] = useState<string | undefined>(undefined);
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const user = loadUser();
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const loadedConversationRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    void refreshConversations().catch(() => undefined);
  }, []);

  useEffect(() => {
    // The URL is the source of truth for the active conversation. Load its
    // history whenever the param changes — unless it's the conversation already
    // on screen (e.g. one we just created), which would wipe the streamed turns.
    if (conversationId === loadedConversationRef.current) {
      return;
    }
    loadedConversationRef.current = conversationId;
    if (!conversationId) {
      setMessages([]);
      return;
    }
    void loadHistory(conversationId);
  }, [conversationId]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  async function refreshConversations(): Promise<ConversationSummary[]> {
    const summaries = await listConversations();
    setConversations(summaries);
    return summaries;
  }

  async function loadHistory(id: string) {
    try {
      const history = await getConversationHistory(id);
      setMessages(
        history.turns.map((turn) => ({
          role: turn.role === "user" ? "user" : "assistant",
          content: turn.content,
          riskLevel: turn.role === "assistant" ? extractRiskLevel(turn.content) : undefined,
        }))
      );
    } catch {
      setMessages([]);
    }
  }

  function openConversation(id: string) {
    if (loading) {
      return;
    }
    navigate(`/chat/${id}`);
  }

  function handleNewConversation() {
    if (loading) {
      return;
    }
    navigate("/chat");
  }

  function handleLogout() {
    localStorage.removeItem("acme_token");
    localStorage.removeItem("acme_user");
    navigate("/login");
  }

  async function handleSend(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || loading) {
      return;
    }

    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setInput("");
    setLoading(true);
    setStreamingStatus(undefined);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    function updateLastMessage(update: Partial<DisplayMessage> | ((message: DisplayMessage) => DisplayMessage)) {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = typeof update === "function" ? update(last) : { ...last, ...update };
        return next;
      });
    }

    try {
      await streamMessage(
        text,
        conversationId,
        {
          onStatus: (statusText) => {
            setStreamingStatus(statusText);
            updateLastMessage({ content: "" });
          },
          onToken: (content) => {
            setStreamingStatus(undefined);
            updateLastMessage((message) => ({ ...message, content: message.content + content }));
          },
          onDone: (response) => {
            updateLastMessage({
              content: response.response,
              toolsCalled: response.tools_called,
              riskLevel: extractRiskLevel(response.response),
            });
            if (conversationId !== response.conversation_id) {
              // New conversation: mark it as already loaded so the URL effect
              // won't refetch and wipe the streamed turns, then put it in the URL.
              loadedConversationRef.current = response.conversation_id;
              navigate(`/chat/${response.conversation_id}`);
            }
          },
          onError: () => {
            updateLastMessage({ content: "Something went wrong reaching the agent. Please try again." });
          },
        },
        controller.signal
      );
      await refreshConversations().catch(() => undefined);
    } catch {
      updateLastMessage({ content: "Something went wrong reaching the agent. Please try again." });
    } finally {
      setLoading(false);
      setStreamingStatus(undefined);
      abortControllerRef.current = null;
    }
  }

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <h1 className="text-lg font-semibold text-gray-900">Acme Agent</h1>
        <div className="flex items-center gap-3">
          {user && (
            <span className="text-sm text-gray-600">
              {user.username} <span className="text-gray-300">·</span>{" "}
              <span className="text-gray-400">{user.role}</span>
            </span>
          )}
          <button
            onClick={handleLogout}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100"
          >
            Logout
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="flex w-[250px] flex-shrink-0 flex-col border-r border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Conversations</h2>
            <button
              onClick={handleNewConversation}
              disabled={loading}
              className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50"
            >
              + New
            </button>
          </div>

          <ul className="flex-1 overflow-y-auto">
            {conversations.length === 0 ? (
              <li className="px-4 py-6 text-center text-xs text-gray-400">No conversations yet</li>
            ) : (
              conversations.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    onClick={() => openConversation(conversation.id)}
                    disabled={loading}
                    className={`flex w-full items-start gap-2 border-b border-gray-100 px-4 py-3 text-left hover:bg-gray-100 disabled:opacity-50 ${
                      conversation.id === conversationId ? "bg-gray-200" : ""
                    }`}
                  >
                    <span className="mt-0.5 text-base leading-none">💬</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-gray-900">
                        {conversation.customer_name ?? conversation.preview}
                      </span>
                      {conversation.customer_name && (
                        <span className="block truncate text-xs text-gray-500">{conversation.preview}</span>
                      )}
                      <span className="block text-xs text-gray-400">
                        {formatRelativeTime(conversation.last_turn_at)}
                      </span>
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </aside>

        <div className="flex flex-1 flex-col overflow-hidden">
          <main className="flex-1 overflow-y-auto px-6 py-4">
            <div className="mx-auto flex max-w-2xl flex-col gap-4">
              {messages.length === 0 && (
                <p className="mt-16 text-center text-sm text-gray-400">
                  {conversationId
                    ? "No messages in this conversation yet."
                    : "Start a new conversation by asking about a customer, their open issues, or escalation risk."}
                </p>
              )}

              {messages.map((message, index) => {
                const isPending =
                  loading &&
                  message.role === "assistant" &&
                  index === messages.length - 1 &&
                  message.content === "";

                return (
                  <div key={index} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[80%] rounded-xl px-4 py-3 text-sm shadow-sm ${
                        message.role === "user"
                          ? "bg-gray-900 text-white"
                          : "border border-gray-200 bg-white text-gray-800"
                      }`}
                    >
                      {isPending ? (
                        <div className="flex items-center gap-2 text-gray-400">
                          <span>{streamingStatus ?? "Agent is thinking"}</span>
                          <span className="flex gap-1">
                            <span
                              className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400"
                              style={{ animationDelay: "0ms" }}
                            />
                            <span
                              className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400"
                              style={{ animationDelay: "150ms" }}
                            />
                            <span
                              className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400"
                              style={{ animationDelay: "300ms" }}
                            />
                          </span>
                        </div>
                      ) : (
                        <p className="whitespace-pre-wrap">{message.content}</p>
                      )}

                      {message.role === "assistant" &&
                        !isPending &&
                        ((message.toolsCalled && message.toolsCalled.length > 0) || message.riskLevel) && (
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            {message.toolsCalled?.map((tool, toolIndex) => (
                              <span
                                key={toolIndex}
                                className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600"
                              >
                                {tool}
                              </span>
                            ))}
                            {message.riskLevel && (
                              <span
                                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                                  RISK_BADGE_STYLES[message.riskLevel] ?? "bg-gray-100 text-gray-600"
                                }`}
                              >
                                Risk: {message.riskLevel}
                              </span>
                            )}
                          </div>
                        )}
                    </div>
                  </div>
                );
              })}

              <div ref={bottomRef} />
            </div>
          </main>

          <form onSubmit={handleSend} className="border-t border-gray-200 bg-white px-6 py-4">
            <div className="mx-auto flex max-w-2xl gap-2">
              <input
                type="text"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask about a customer, an issue, or an escalation..."
                className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-gray-800 disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
