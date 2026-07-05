const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

// 定义数据类型
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

export type GrowthReportResponse = {
  sessionId: string;
  status: "not_found" | "success" | "failed" | "partial" | "generating";
  workflowRunId?: string | null;
  reportId?: number | null;
  reportUid?: string | null;
  report?: Record<string, unknown> | null;
  errorMessage?: string | null;
  missingInputs?: string[];
  branch?: string | null;
  branchReason?: string | null;
  nextActions?: Array<Record<string, unknown>>;
};

export type WorkflowRunStatus = "running" | "waiting_user" | "failed" | "success" | "partial";

export type WorkflowRunResumeReason =
  | "new_user_input"
  | "unfinished_turn"
  | "failed_retry"
  | "new_trigger"
  | "unfinished_run"
  | "already_completed";

export type WorkflowRunListItem = {
  workflowRunId: string;
  workflowId: string;
  threadId?: string | null;
  projectId?: number | null;
  sessionId?: number | null;
  status: WorkflowRunStatus;
  currentStep?: string | null;
  activeStep?: string | null;
  resumeReason?: WorkflowRunResumeReason | null;
  resumeFromStep?: string | null;
  completedSteps: string[];
  failedSteps: string[];
  missingRequiredSteps: string[];
  errorMessage?: string | null;
  stepCount: number;
  agentRunCount: number;
  latestAgentRunId?: number | null;
  createTime?: string | null;
  updateTime?: string | null;
};

export type WorkflowRunListResponse = {
  items: WorkflowRunListItem[];
  total: number;
};

export type WorkflowRunStepSummary = {
  stepId: string;
  required: boolean;
  status: "missing" | "running" | "waiting_user" | "failed" | "success" | "skipped";
  agentRunIds: number[];
  latestAgentRunId?: number | null;
  latestStatus?: string | null;
  runCount: number;
  missing: boolean;
};

export type AgentRunWorkflowSummary = {
  workflowId?: string | null;
  workflowRunId?: string | null;
  stepId?: string | null;
};

export type AgentRunListItem = {
  id: number;
  agentName: string;
  taskName: string;
  promptId: string;
  promptVersion: string;
  modelName?: string | null;
  projectId?: number | null;
  sessionId?: number | null;
  status: string;
  evidenceRefs: string[];
  workflow: AgentRunWorkflowSummary;
  errorMessage?: string | null;
  createTime: string;
};

export type WorkflowRunDetailResponse = WorkflowRunListItem & {
  steps: WorkflowRunStepSummary[];
  agentRuns: AgentRunListItem[];
  state?: Record<string, unknown> | null;
  lastError?: Record<string, unknown> | null;
};

export type WorkflowRunReconciliationCheck = {
  name: string;
  ok: boolean;
  level: "info" | "warning" | "error" | string;
  detail: string;
};

export type WorkflowRunReconciliationResponse = {
  ok: boolean;
  errors: string[];
  warnings: string[];
  checks: WorkflowRunReconciliationCheck[];
  metadata: Record<string, unknown>;
};

//  核心请求封装，统一处理所有的HTTP请求
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

// 基于request函数封装了五个相关的API
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

export async function getGrowthReport(sessionId: string) {
  return request<GrowthReportResponse>(`/interview/${encodeURIComponent(sessionId)}/growth-report`);
}

export async function generateGrowthReport(sessionId: string) {
  return request<GrowthReportResponse>(
    `/interview/${encodeURIComponent(sessionId)}/growth-report/generate`,
    {
      method: "POST",
    },
  );
}

export async function listWorkflowRuns(filters?: {
  status?: WorkflowRunStatus | "";
  workflowId?: string;
}) {
  const params = new URLSearchParams();
  if (filters?.status) {
    params.set("status", filters.status);
  }
  if (filters?.workflowId) {
    params.set("workflowId", filters.workflowId);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  return request<WorkflowRunListResponse>(`/workflow-runs${query}`);
}

export async function getWorkflowRunDetail(workflowRunId: string) {
  return request<WorkflowRunDetailResponse>(`/workflow-runs/${encodeURIComponent(workflowRunId)}`);
}

export async function getWorkflowRunReconciliation(workflowRunId: string) {
  return request<WorkflowRunReconciliationResponse>(
    `/workflow-runs/${encodeURIComponent(workflowRunId)}/reconciliation`,
  );
}

// 当前没有处理鉴权，需要在请求头中加入相应的认证信息（如Token）才能访问需要鉴权的接口
//  对于流式响应或者长耗时请求还没有处理
// 当前全局错误提示只是简单的抛出错误
