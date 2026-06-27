const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

export type ChatMessage = {
  roleType: "user" | "assistant";
  messageType: "question" | "answer" | "followup" | "summary";
  roundNo: number;
  content: string;
  createTime?: string;
};

export type Evaluation = {
  strengths: string;
  weaknesses: string;
  suggestions: string;
  technicalAbility?: string;
  projectExperience?: string;
  communication?: string;
  improvementSuggestions?: string;
  summary?: string | null;
};

export type HistoryResponse = {
  sessionId: string;
  roleName: string;
  status: string;
  messages: ChatMessage[];
  evaluation: Evaluation | null;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function startInterview(roleName: string) {
  return request<{ sessionId: string; reply: string }>("/interview/start", {
    method: "POST",
    body: JSON.stringify({ roleName }),
  });
}

export async function sendMessage(sessionId: string, message: string) {
  return request<{ reply: string; roundNo: number }>("/interview/chat", {
    method: "POST",
    body: JSON.stringify({ sessionId, message }),
  });
}

export async function endInterview(sessionId: string) {
  return request<{ evaluation: Evaluation }>("/interview/end", {
    method: "POST",
    body: JSON.stringify({ sessionId }),
  });
}

export async function getHistory(sessionId: string) {
  return request<HistoryResponse>(`/interview/history/${sessionId}`);
}

export async function deleteInterview(sessionId: string) {
  return request<{ success: boolean }>(`/interview/delete/${sessionId}`, {
    method: "DELETE",
  });
}
