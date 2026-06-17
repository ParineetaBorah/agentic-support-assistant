export interface User {
  username: string;
  role: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  tools_called: string[];
  turn_count: number;
  cost_usd: number;
  total_tokens: number;
}

export interface ToolCall {
  name: string;
  status: "success" | "error";
}

export interface ConversationTurn {
  role: string;
  content: string;
  created_at: string;
  tools_called: string[];
}

export interface ConversationHistory {
  conversation_id: string;
  turns: ConversationTurn[];
}

export interface ConversationSummary {
  id: string;
  started_at: string;
  last_turn_at: string;
  turn_count: number;
  preview: string;
}
