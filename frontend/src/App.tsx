import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Copy,
  FileText,
  History,
  Loader2,
  MessageCircle,
  Play,
  RefreshCw,
  Route,
  Send,
  Square,
  Target,
  Trash2,
} from "lucide-react";

import {
  ChatMessage,
  Evaluation,
  GrowthReportResponse,
  WorkflowRunDetailResponse,
  WorkflowRunListItem,
  WorkflowRunReconciliationResponse,
  WorkflowRunStatus,
  deleteInterview,
  endInterview,
  generateGrowthReport,
  getGrowthReport,
  getWorkflowRunDetail,
  getWorkflowRunReconciliation,
  getHistory,
  listWorkflowRuns,
  sendMessage,
  startInterview,
} from "./api";

// 定义一个常量数组，存放可选的面试岗位
const ROLE_OPTIONS = ["Java后端", "测试开发", "AI应用开发", "前端开发", "Go后端"];

function App() {
  const [activeView, setActiveView] = useState<"interview" | "workflowRuns">("interview");
  const [initialWorkflowFilter, setInitialWorkflowFilter] = useState("");
  // 定义各种状态，当前选中的岗位，默认是数组第一个"Java后端"。setRoleName 是用来修改它的工具
  //  evaluation面试结束后的评价报告。`Evaluation | null` 表示“要么是评价数据，要么是空(null)”
  const [roleName, setRoleName] = useState(ROLE_OPTIONS[0]);
  const [sessionId, setSessionId] = useState("");
  const [historySessionId, setHistorySessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [growthReport, setGrowthReport] = useState<GrowthReportResponse | null>(null);
  const [growthReportLoading, setGrowthReportLoading] = useState(false);
  const [growthReportError, setGrowthReportError] = useState("");
  const [status, setStatus] = useState<"idle" | "active" | "finished">("idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  //  如果出错了，这里可以显示错误信息

  //  只有当状态是 active，有sessionId，且不在加载中时，这个值才是true，表示可以发送消息
  const canChat = status === "active" && sessionId && !loading;

  const title = useMemo(() => {
    if (status === "idle") return "准备开始";
    if (status === "active") return `${roleName} 模拟面试`;
    return "面试评价";
  }, [roleName, status]);

  //  用户点击“开始面试”按钮时，调用startInterview接口，获取sessionId和第一条问题，并更新状态
  async function handleStart() {
    setLoading(true);
    setError("");
    setEvaluation(null); // 清空之前的评价
    setGrowthReport(null);
    setGrowthReportError("");
    try {
      const result = await startInterview(roleName);
      setSessionId(result.sessionId);
      setHistorySessionId(result.sessionId);
      setStatus("active");
      setMessages([
        {
          roleType: "assistant",
          messageType: "question",
          roundNo: 1,
          content: result.reply,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动面试失败");
    } finally {
      setLoading(false);
    }
  }

//  用户发送消息
  async function handleSubmit(event: FormEvent) {
    event.preventDefault(); // 阻止表单默认的刷新页面行为
    const content = input.trim(); // 去掉输入内容前后的空格
    if (!content || !canChat) return; // 没输入内容或不能聊天，直接退出

    const nextRoundNo = Math.max(1, ...messages.map((item) => item.roundNo)) + 1;
    setInput("");
    setMessages((current) => [
      ...current, // 保留之前的消息
      {
        roleType: "user",
        messageType: "answer",
        roundNo: nextRoundNo,
        content,
      },
    ]);

    setLoading(true);
    setError("");
    try {
      const result = await sendMessage(sessionId, content); // 发给后端
      setMessages((current) => [ // 把 AI 的话也加到屏幕上
        ...current,
        {
          roleType: "assistant",
          messageType: "followup",
          roundNo: result.roundNo,
          content: result.reply,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送回答失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleEnd() {
    if (!sessionId) return;
    setLoading(true);
    setError("");
    try {
      const result = await endInterview(sessionId);
      setEvaluation(result.evaluation);
      setStatus("finished");
      await loadGrowthReport(sessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成评价失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadHistory() {
    const id = historySessionId.trim();
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      const result = await getHistory(id);
      setSessionId(result.sessionId);
      setRoleName(result.roleName);
      setMessages(result.messages);
      setEvaluation(result.evaluation);
      setGrowthReport(null);
      setGrowthReportError("");
      setStatus(result.status === "finished" ? "finished" : "active");
      if (result.status === "finished") {
        await loadGrowthReport(result.sessionId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "查询历史失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    const id = sessionId || historySessionId.trim();
    if (!id) return;

    setLoading(true);
    setError("");
    try {
      await deleteInterview(id);
      setSessionId("");
      setHistorySessionId("");
      setMessages([]);
      setEvaluation(null);
      setGrowthReport(null);
      setGrowthReportError("");
      setStatus("idle");
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除会话失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadGrowthReport(id = sessionId) {
    if (!id) return;
    setGrowthReportLoading(true);
    setGrowthReportError("");
    try {
      const result = await getGrowthReport(id);
      setGrowthReport(result);
    } catch (err) {
      setGrowthReportError(err instanceof Error ? err.message : "Load growth report failed");
    } finally {
      setGrowthReportLoading(false);
    }
  }

  async function handleGenerateGrowthReport() {
    if (!sessionId) return;
    setGrowthReportLoading(true);
    setGrowthReportError("");
    try {
      const result = await generateGrowthReport(sessionId);
      setGrowthReport(result);
    } catch (err) {
      setGrowthReportError(err instanceof Error ? err.message : "Generate growth report failed");
    } finally {
      setGrowthReportLoading(false);
    }
  }

  //  JSX 允许在 JS 里直接写 HTML 标签,这里就是看到的页面长相
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="brand">Interview Agent V1</div>
          <h1>{title}</h1>
        </div>

        <nav className="view-switcher" aria-label="Primary views">
          <button
            className={activeView === "interview" ? "view-button view-button-active" : "view-button"}
            type="button"
            onClick={() => setActiveView("interview")}
          >
            <MessageCircle size={18} />
            Interview
          </button>
          <button
            className={activeView === "workflowRuns" ? "view-button view-button-active" : "view-button"}
            type="button"
            onClick={() => setActiveView("workflowRuns")}
          >
            <Route size={18} />
            Workflow Runs
          </button>
        </nav>

        <section className="panel">
          <label htmlFor="role">目标岗位</label>
          <select id="role" value={roleName} onChange={(event) => setRoleName(event.target.value)}>
            {ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <button className="primary-button" type="button" onClick={handleStart} disabled={loading}>
            {loading && status === "idle" ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            开始面试
          </button>
        </section>

        <section className="panel">
          <label htmlFor="session">Session ID</label>
          <input
            id="session"
            value={historySessionId}
            onChange={(event) => setHistorySessionId(event.target.value)}
            placeholder="输入 sessionId 查询"
          />
          <button type="button" onClick={handleLoadHistory} disabled={loading || !historySessionId.trim()}>
            <History size={18} />
            查询历史
          </button>
          <button type="button" onClick={handleDelete} disabled={loading || (!sessionId && !historySessionId.trim())}>
            <Trash2 size={18} />
            删除会话
          </button>
        </section>

        {sessionId && (
          <section className="session-box">
            <span>当前会话</span>
            <code>{sessionId}</code>
          </section>
        )}
      </aside>

      {activeView === "interview" ? (
      <section className="workspace">
        {error && <div className="error-banner">{error}</div>}

        <div className="chat-board">
          {messages.length === 0 ? (
            <div className="empty-state">
              <MessageCircle size={40} />
              <p>选择岗位后开始一场 V1 模拟面试。</p>
            </div>
          ) : (
            messages.map((message, index) => (
              <article
                className={`message ${message.roleType === "user" ? "message-user" : "message-assistant"}`}
                key={`${message.roleType}-${message.roundNo}-${index}`}
              >
                <div className="message-meta">
                  <span>{message.roleType === "user" ? "候选人" : "面试官"}</span>
                  <span>第 {message.roundNo} 轮</span>
                </div>
                <p>{message.content}</p>
              </article>
            ))
          )}
        </div>

        {evaluation && (
          <section className="evaluation">
            <h2>综合评价</h2>
            <div className="evaluation-grid">
              <div>
                <h3>技术能力</h3>
                <p>{evaluation.technicalAbility || evaluation.strengths}</p>
              </div>
              <div>
                <h3>项目经验</h3>
                <p>{evaluation.projectExperience || evaluation.weaknesses}</p>
              </div>
              <div>
                <h3>沟通表达</h3>
                <p>{evaluation.communication || evaluation.strengths}</p>
              </div>
              <div>
                <h3>改进建议</h3>
                <p>{evaluation.improvementSuggestions || evaluation.suggestions}</p>
              </div>
              {evaluation.summary && (
                <div className="evaluation-summary">
                  <h3>总结</h3>
                  <p>{evaluation.summary}</p>
                </div>
              )}
            </div>
          </section>
        )}

        {status === "finished" && (
          <GrowthReportPanel
            error={growthReportError}
            loading={growthReportLoading}
            reportResponse={growthReport}
            onGenerate={handleGenerateGrowthReport}
            onRefresh={() => void loadGrowthReport()}
            onOpenWorkflow={(workflowRunId) => {
              setInitialWorkflowFilter("candidate_growth_report");
              setActiveView("workflowRuns");
            }}
          />
        )}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={canChat ? "输入你的回答..." : "开始面试后可输入回答"}
            disabled={!canChat}
          />
          <div className="composer-actions">
            <button type="button" onClick={handleEnd} disabled={!sessionId || status !== "active" || loading}>
              <Square size={18} />
              结束
            </button>
            <button className="primary-button" type="submit" disabled={!input.trim() || !canChat}>
              {loading && status === "active" ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
              发送
            </button>
          </div>
        </form>
      </section>
      ) : (
        <WorkflowRunsView initialWorkflowId={initialWorkflowFilter} />
      )}
    </main>
  );
}

type GrowthReportPanelProps = {
  error: string;
  loading: boolean;
  reportResponse: GrowthReportResponse | null;
  onGenerate: () => void;
  onRefresh: () => void;
  onOpenWorkflow: (workflowRunId: string) => void;
};

function GrowthReportPanel({
  error,
  loading,
  onGenerate,
  onOpenWorkflow,
  onRefresh,
  reportResponse,
}: GrowthReportPanelProps) {
  const report = getRecord(reportResponse?.report);
  const status = reportResponse?.status ?? "not_found";
  const hasReport = status === "success" && Boolean(report);
  const summary = getRecord(report?.overall_summary);
  const jobMatch = getRecord(report?.job_match);
  const storytelling = getRecord(report?.project_storytelling);
  const workflowRunId = reportResponse?.workflowRunId || "";

  return (
    <section className="growth-report">
      <header className="growth-report-header">
        <div>
          <p className="eyebrow">Growth Report</p>
          <h2>候选人成长报告</h2>
        </div>
        <div className="growth-report-actions">
          {workflowRunId && (
            <button type="button" onClick={() => onOpenWorkflow(workflowRunId)}>
              <Route size={18} />
              Workflow
            </button>
          )}
          {hasReport && (
            <button type="button" onClick={onRefresh} disabled={loading}>
              {loading ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
              Refresh
            </button>
          )}
          {!hasReport && (
            <button className="primary-button" type="button" onClick={onGenerate} disabled={loading}>
              {loading ? <Loader2 className="spin" size={18} /> : <FileText size={18} />}
              生成报告
            </button>
          )}
        </div>
      </header>

      {error && <div className="growth-report-error">{error}</div>}

      {loading && !hasReport && (
        <div className="growth-report-empty">
          <Loader2 className="spin" size={28} />
          <p>正在生成成长报告...</p>
        </div>
      )}

      {!loading && status === "not_found" && (
        <div className="growth-report-empty">
          <FileText size={30} />
          <p>面试评价已完成，可以生成结构化成长报告。</p>
        </div>
      )}

      {!loading && status === "partial" && (
        <div className="growth-report-error">
          {reportResponse?.errorMessage || "成长报告缺少必要输入，暂时只能生成部分结果。"}
        </div>
      )}

      {!loading && status === "failed" && (
        <div className="growth-report-error">
          {reportResponse?.errorMessage || "成长报告生成失败，请重试。"}
        </div>
      )}

      {hasReport && report && (
        <div className="growth-report-body">
          <section className="growth-summary-grid">
            <GrowthSummaryCard
              icon={<Target size={18} />}
              label="Overall"
              title={getString(summary?.level, "unknown")}
              value={getString(summary?.summary, "暂无总结")}
            />
            <GrowthSummaryCard
              icon={<AlertTriangle size={18} />}
              label="Top Risk"
              title={getString(summary?.top_risk, "暂无风险")}
              value={getString(summary?.next_priority, "暂无下一步优先级")}
            />
            <GrowthSummaryCard
              icon={<BookOpen size={18} />}
              label="Job Match"
              title={getString(jobMatch?.level, "unknown")}
              value={growthListPreview(getArray(jobMatch?.matched_points), "暂无岗位匹配点")}
            />
          </section>

          <section className="growth-section-grid">
            <GrowthListSection
              title="技术优势"
              items={getArray(report.technical_strengths)}
              emptyText="暂无技术优势条目"
              renderItem={(item) => {
                const record = getRecord(item);
                return (
                  <>
                    <strong>{getString(record?.skill, "未命名能力")}</strong>
                    <p>{getString(record?.description, "暂无说明")}</p>
                  </>
                );
              }}
            />
            <GrowthListSection
              title="技术短板"
              items={getArray(report.technical_gaps)}
              emptyText="暂无技术短板条目"
              renderItem={(item) => {
                const record = getRecord(item);
                return (
                  <>
                    <div className="growth-item-title-row">
                      <strong>{getString(record?.skill, "未命名短板")}</strong>
                      <span className="priority-pill">{getString(record?.priority, "medium")}</span>
                    </div>
                    <p>{getString(record?.gap, "暂无差距说明")}</p>
                    <small>{getString(record?.improvement_action, "暂无行动建议")}</small>
                  </>
                );
              }}
            />
            <GrowthListSection
              title="简历优化"
              items={getArray(report.resume_suggestions)}
              emptyText="暂无简历优化建议"
              renderItem={(item) => {
                const record = getRecord(item);
                return (
                  <>
                    <div className="growth-item-title-row">
                      <strong>{getString(record?.section, "resume")}</strong>
                      <span className="priority-pill">{getString(record?.priority, "medium")}</span>
                    </div>
                    <p>{getString(record?.problem, "暂无问题说明")}</p>
                    <small>{getString(record?.suggestion, "暂无优化建议")}</small>
                  </>
                );
              }}
            />
            <GrowthListSection
              title="下一轮训练"
              items={getArray(report.next_interview_focus)}
              emptyText="暂无下一轮训练重点"
              renderItem={(item) => {
                const record = getRecord(item);
                return (
                  <>
                    <strong>{getString(record?.topic, "未命名主题")}</strong>
                    <p>{getString(record?.reason, "暂无原因")}</p>
                    <small>{getString(record?.sample_question, "暂无样例问题")}</small>
                  </>
                );
              }}
            />
          </section>

          <section className="growth-wide-section">
            <h3>项目表达</h3>
            <div className="growth-chip-grid">
              {getArray(storytelling?.strengths).map((item, index) => (
                <span className="growth-chip growth-chip-good" key={`story-strength-${index}`}>
                  {stringifyValue(item)}
                </span>
              ))}
              {getArray(storytelling?.risks).map((item, index) => (
                <span className="growth-chip growth-chip-risk" key={`story-risk-${index}`}>
                  {stringifyValue(item)}
                </span>
              ))}
              {getArray(storytelling?.suggestions).map((item, index) => (
                <span className="growth-chip" key={`story-suggestion-${index}`}>
                  {stringifyValue(item)}
                </span>
              ))}
            </div>
          </section>

          <GrowthListSection
            className="growth-wide-section"
            title="学习行动计划"
            items={getArray(report.learning_plan)}
            emptyText="暂无学习计划"
            renderItem={(item) => {
              const record = getRecord(item);
              return (
                <>
                  <div className="growth-item-title-row">
                    <strong>{getString(record?.day_range, "next")}</strong>
                    <span>{getString(record?.goal, "暂无目标")}</span>
                  </div>
                  <p>{getArray(record?.tasks).map(stringifyValue).join(" / ") || "暂无任务"}</p>
                  <small>{getString(record?.expected_output, "暂无交付物")}</small>
                </>
              );
            }}
          />
        </div>
      )}
    </section>
  );
}

function GrowthSummaryCard({
  icon,
  label,
  title,
  value,
}: {
  icon: ReactNode;
  label: string;
  title: string;
  value: string;
}) {
  return (
    <article className="growth-summary-card">
      <div>
        {icon}
        <span>{label}</span>
      </div>
      <strong>{title}</strong>
      <p>{value}</p>
    </article>
  );
}

function GrowthListSection({
  className = "",
  emptyText,
  items,
  renderItem,
  title,
}: {
  className?: string;
  emptyText: string;
  items: unknown[];
  renderItem: (item: unknown, index: number) => ReactNode;
  title: string;
}) {
  return (
    <section className={`growth-list-section ${className}`}>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted">{emptyText}</p>
      ) : (
        <div className="growth-list">
          {items.map((item, index) => (
            <article className="growth-list-item" key={`${title}-${index}`}>
              {renderItem(item, index)}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function getRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function getArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function getString(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function stringifyValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return getString(record.title) || getString(record.reason) || getString(record.suggestion) || JSON.stringify(value);
  }
  return "";
}

function growthListPreview(items: unknown[], fallback: string): string {
  const preview = items
    .slice(0, 2)
    .map((item) => {
      const record = getRecord(item);
      return getString(record?.title) || stringifyValue(item);
    })
    .filter(Boolean)
    .join(" / ");
  return preview || fallback;
}

const WORKFLOW_STATUS_OPTIONS: Array<WorkflowRunStatus | ""> = [
  "",
  "waiting_user",
  "running",
  "failed",
  "success",
  "partial",
];

const WORKFLOW_ID_OPTIONS = [
  "",
  "interview_runtime",
  "post_interview_assessment",
  "candidate_growth_report",
  "preparation",
  "resume_optimization",
];

function WorkflowRunsView({ initialWorkflowId = "" }: { initialWorkflowId?: string }) {
  const [runs, setRuns] = useState<WorkflowRunListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<WorkflowRunStatus | "">("");
  const [workflowFilter, setWorkflowFilter] = useState(initialWorkflowId);
  const [selectedWorkflowRunId, setSelectedWorkflowRunId] = useState("");
  const [detail, setDetail] = useState<WorkflowRunDetailResponse | null>(null);
  const [reconciliation, setReconciliation] = useState<WorkflowRunReconciliationResponse | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [reconciliationError, setReconciliationError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");

  async function loadRuns(nextStatus = statusFilter, nextWorkflowId = workflowFilter) {
    setLoadingRuns(true);
    setError("");
    try {
      const result = await listWorkflowRuns({
        status: nextStatus,
        workflowId: nextWorkflowId,
      });
      setRuns(result.items);
      if (
        selectedWorkflowRunId &&
        !result.items.some((item) => item.workflowRunId === selectedWorkflowRunId)
      ) {
        setSelectedWorkflowRunId("");
        setDetail(null);
        setReconciliation(null);
        setDetailError("");
        setReconciliationError("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load workflow runs failed");
    } finally {
      setLoadingRuns(false);
    }
  }

  async function loadDetail(workflowRunId: string) {
    setSelectedWorkflowRunId(workflowRunId);
    setLoadingDetail(true);
    setDetailError("");
    setReconciliationError("");
    setCopyMessage("");
    try {
      const [detailResult, reconciliationResult] = await Promise.all([
        getWorkflowRunDetail(workflowRunId),
        getWorkflowRunReconciliation(workflowRunId),
      ]);
      setDetail(detailResult);
      setReconciliation(reconciliationResult);
    } catch (err) {
      setDetail(null);
      setReconciliation(null);
      setDetailError(err instanceof Error ? err.message : "Load workflow run detail failed");
    } finally {
      setLoadingDetail(false);
    }
  }

  useEffect(() => {
    if (initialWorkflowId) {
      setWorkflowFilter(initialWorkflowId);
    }
    void loadRuns(statusFilter, initialWorkflowId || workflowFilter);
  }, [initialWorkflowId]);

  function handleStatusChange(nextStatus: WorkflowRunStatus | "") {
    setStatusFilter(nextStatus);
    void loadRuns(nextStatus, workflowFilter);
  }

  function handleWorkflowChange(nextWorkflowId: string) {
    setWorkflowFilter(nextWorkflowId);
    void loadRuns(statusFilter, nextWorkflowId);
  }

  function handleRefresh() {
    void loadRuns(statusFilter, workflowFilter);
    if (selectedWorkflowRunId) {
      void loadDetail(selectedWorkflowRunId);
    }
  }

  async function handleCopyWorkflowRunId(workflowRunId: string) {
    setCopyMessage("");
    try {
      await navigator.clipboard.writeText(workflowRunId);
      setCopyMessage("workflowRunId copied");
    } catch {
      setCopyMessage("copy unavailable");
    }
  }

  return (
    <section className="workflow-workspace">
      <header className="workflow-header">
        <div>
          <p className="eyebrow">Runtime Observability</p>
          <h2>Workflow Runs</h2>
        </div>
        <div className="workflow-actions">
          <select
            aria-label="Workflow id filter"
            value={workflowFilter}
            onChange={(event) => handleWorkflowChange(event.target.value)}
          >
            {WORKFLOW_ID_OPTIONS.map((item) => (
              <option key={item || "all"} value={item}>
                {item || "all workflows"}
              </option>
            ))}
          </select>
          <select
            aria-label="Workflow status filter"
            value={statusFilter}
            onChange={(event) => handleStatusChange(event.target.value as WorkflowRunStatus | "")}
          >
            {WORKFLOW_STATUS_OPTIONS.map((item) => (
              <option key={item || "all"} value={item}>
                {item || "all statuses"}
              </option>
            ))}
          </select>
          <button type="button" onClick={handleRefresh} disabled={loadingRuns || loadingDetail}>
            {loadingRuns ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
            Refresh
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="workflow-summary">
        <Metric label="Total" value={runs.length.toString()} onClick={() => handleStatusChange("")} />
        <Metric
          label="Failed"
          value={countByStatus(runs, "failed").toString()}
          tone="failed"
          onClick={() => handleStatusChange("failed")}
        />
        <Metric
          label="Running"
          value={countByStatus(runs, "running").toString()}
          tone="running"
          onClick={() => handleStatusChange("running")}
        />
        <Metric
          label="Waiting"
          value={countByStatus(runs, "waiting_user").toString()}
          tone="waiting"
          onClick={() => handleStatusChange("waiting_user")}
        />
      </section>

      <div className="workflow-table-shell">
        <table className="workflow-table">
          <thead>
            <tr>
              <th>Workflow Run</th>
              <th>Status</th>
              <th>Current Step</th>
              <th>Active Step</th>
              <th>Resume</th>
              <th>Error</th>
              <th>AgentRuns</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 ? (
              <tr>
                <td className="workflow-empty-cell" colSpan={8}>
                  {loadingRuns ? "Loading workflow runs..." : "No workflow runs found."}
                </td>
              </tr>
            ) : (
              runs.map((run) => (
                <tr
                  className={[
                    "workflow-row",
                    `workflow-row-${run.status}`,
                    selectedWorkflowRunId === run.workflowRunId ? "workflow-row-selected" : "",
                  ].join(" ")}
                  key={run.workflowRunId}
                  onClick={() => void loadDetail(run.workflowRunId)}
                >
                  <td>
                    <div className="workflow-id-cell">
                      <strong>{run.workflowRunId}</strong>
                      <span>{run.workflowId}</span>
                      {run.threadId && <code>{run.threadId}</code>}
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{run.currentStep || "-"}</td>
                  <td>{run.activeStep || "-"}</td>
                  <td>{run.resumeReason || "-"}</td>
                  <td>{run.errorMessage || "-"}</td>
                  <td>{run.agentRunCount}</td>
                  <td>{formatDateTime(run.updateTime || run.createTime)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <WorkflowRunDetailPanel
        detail={detail}
        detailError={detailError}
        loading={loadingDetail}
        copyMessage={copyMessage}
        reconciliation={reconciliation}
        reconciliationError={reconciliationError}
        onCopyWorkflowRunId={handleCopyWorkflowRunId}
        onRefreshDetail={() => void loadDetail(selectedWorkflowRunId)}
        selectedWorkflowRunId={selectedWorkflowRunId}
      />
    </section>
  );
}

function Metric({
  label,
  onClick,
  value,
  tone = "default",
}: {
  label: string;
  onClick?: () => void;
  value: string;
  tone?: "default" | "failed" | "running" | "waiting";
}) {
  if (onClick) {
    return (
      <button className={`metric metric-${tone} metric-button`} type="button" onClick={onClick}>
        <span>{label}</span>
        <strong>{value}</strong>
      </button>
    );
  }

  return (
    <div className={`metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusBadge({ status }: { status: WorkflowRunStatus }) {
  return <span className={`status-badge status-${status}`}>{status}</span>;
}

function WorkflowRunDetailPanel({
  copyMessage,
  detail,
  detailError,
  loading,
  onCopyWorkflowRunId,
  onRefreshDetail,
  reconciliation,
  reconciliationError,
  selectedWorkflowRunId,
}: {
  copyMessage: string;
  detail: WorkflowRunDetailResponse | null;
  detailError: string;
  loading: boolean;
  onCopyWorkflowRunId: (workflowRunId: string) => void;
  onRefreshDetail: () => void;
  reconciliation: WorkflowRunReconciliationResponse | null;
  reconciliationError: string;
  selectedWorkflowRunId: string;
}) {
  if (!selectedWorkflowRunId) {
    return (
      <section className="workflow-detail workflow-detail-empty">
        <Route size={28} />
        <p>Select a workflow run to inspect state, errors, steps, and AgentRuns.</p>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="workflow-detail workflow-detail-empty">
        <Loader2 className="spin" size={28} />
        <p>Loading {selectedWorkflowRunId}...</p>
      </section>
    );
  }

  if (detailError) {
    return <div className="error-banner">{detailError}</div>;
  }

  if (!detail) return null;

  return (
    <section className="workflow-detail">
      <header className="workflow-detail-header">
        <div>
          <p className="eyebrow">Workflow Detail</p>
          <h3>{detail.workflowRunId}</h3>
          {copyMessage && <span className="copy-message">{copyMessage}</span>}
        </div>
        <div className="detail-actions">
          <StatusBadge status={detail.status} />
          <button type="button" onClick={() => onCopyWorkflowRunId(detail.workflowRunId)}>
            <Copy size={18} />
            Copy ID
          </button>
          <button type="button" onClick={onRefreshDetail}>
            <RefreshCw size={18} />
            Refresh Detail
          </button>
        </div>
      </header>

      <div className="detail-grid">
        <DetailField label="Workflow" value={detail.workflowId} />
        <DetailField label="Thread" value={detail.threadId || "-"} />
        <DetailField label="Current Step" value={detail.currentStep || "-"} />
        <DetailField label="Active Step" value={detail.activeStep || "-"} />
        <DetailField label="Resume Reason" value={detail.resumeReason || "-"} />
        <DetailField label="Resume From" value={detail.resumeFromStep || "-"} />
        <DetailField label="Branch" value={stringStateValue(detail.state?.branch)} />
        <DetailField label="Branch Reason" value={stringStateValue(detail.state?.branch_reason)} />
        <DetailField label="AgentRuns" value={detail.agentRunCount.toString()} />
        <DetailField label="Updated" value={formatDateTime(detail.updateTime || detail.createTime)} />
      </div>

      {detail.errorMessage && <div className="detail-error">{detail.errorMessage}</div>}
      <ReconciliationPanel reconciliation={reconciliation} error={reconciliationError} />

      <section className="detail-section">
        <h4>Steps</h4>
        <div className="steps-grid">
          {detail.steps.map((step) => (
            <article className={`step-item step-item-${step.status}`} key={step.stepId}>
              <div>
                <strong>{step.stepId}</strong>
                <span>{step.required ? "required" : "optional"}</span>
              </div>
              <StatusText value={step.status} />
              <small>
                runs {step.runCount}
                {step.latestAgentRunId ? ` · latest #${step.latestAgentRunId}` : ""}
              </small>
            </article>
          ))}
        </div>
      </section>

      <section className="detail-section">
        <h4>AgentRuns</h4>
        {detail.agentRuns.length === 0 ? (
          <p className="muted">No AgentRuns linked to this workflow run.</p>
        ) : (
          <div className="agent-run-list">
            {detail.agentRuns.map((run) => (
              <article className="agent-run-item" key={run.id}>
                <div>
                  <strong>#{run.id}</strong>
                  <span>{run.agentName}</span>
                  <code>{run.workflow.stepId || "-"}</code>
                </div>
                <StatusText value={run.status} />
                <small>{formatDateTime(run.createTime)}</small>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="detail-json-grid">
        <JsonBlock label="State" value={detail.state || {}} />
        <JsonBlock label="Last Error" value={detail.lastError || null} />
      </section>
    </section>
  );
}

function ReconciliationPanel({
  error,
  reconciliation,
}: {
  error: string;
  reconciliation: WorkflowRunReconciliationResponse | null;
}) {
  if (error) {
    return <div className="detail-error">{error}</div>;
  }

  if (!reconciliation) {
    return (
      <section className="reconciliation-panel">
        <div className="reconciliation-header">
          <div>
            <h4>Reconciliation</h4>
            <span className="muted">No reconciliation result loaded.</span>
          </div>
        </div>
      </section>
    );
  }

  const failingChecks = reconciliation.checks.filter((check) => !check.ok);

  return (
    <section className={`reconciliation-panel ${reconciliation.ok ? "reconciliation-ok" : "reconciliation-failed"}`}>
      <div className="reconciliation-header">
        <div>
          <h4>Reconciliation</h4>
          <span className="muted">
            {reconciliation.errors.length} errors / {reconciliation.warnings.length} warnings
          </span>
        </div>
        <span className={`reconciliation-status ${reconciliation.ok ? "status-ok" : "status-error"}`}>
          {reconciliation.ok ? "aligned" : "needs review"}
        </span>
      </div>

      {(reconciliation.errors.length > 0 || reconciliation.warnings.length > 0) && (
        <div className="reconciliation-issues">
          {reconciliation.errors.map((item) => (
            <div className="reconciliation-issue issue-error" key={`error-${item}`}>
              {item}
            </div>
          ))}
          {reconciliation.warnings.map((item) => (
            <div className="reconciliation-issue issue-warning" key={`warning-${item}`}>
              {item}
            </div>
          ))}
        </div>
      )}

      <div className="reconciliation-checks">
        {(failingChecks.length > 0 ? failingChecks : reconciliation.checks).map((check) => (
          <article className={`reconciliation-check check-${check.level}`} key={check.name}>
            <div>
              <strong>{check.name}</strong>
              <StatusText value={check.ok ? "success" : check.level} />
            </div>
            <p>{check.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-field">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusText({ value }: { value: string }) {
  return <span className={`status-text status-text-${value}`}>{value}</span>;
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="json-block">
      <h4>{label}</h4>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function countByStatus(items: WorkflowRunListItem[], status: WorkflowRunStatus) {
  return items.filter((item) => item.status === status).length;
}

function stringStateValue(value: unknown) {
  if (typeof value === "string" && value.length > 0) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "-";
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default App;
