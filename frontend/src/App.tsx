import { FormEvent, useMemo, useState } from "react";
import { History, Loader2, MessageCircle, Play, Send, Square, Trash2 } from "lucide-react";

import {
  ChatMessage,
  Evaluation,
  deleteInterview,
  endInterview,
  getHistory,
  sendMessage,
  startInterview,
} from "./api";

const ROLE_OPTIONS = ["Java后端", "测试开发", "AI应用开发", "前端开发", "Go后端"];

function App() {
  const [roleName, setRoleName] = useState(ROLE_OPTIONS[0]);
  const [sessionId, setSessionId] = useState("");
  const [historySessionId, setHistorySessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [status, setStatus] = useState<"idle" | "active" | "finished">("idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const canChat = status === "active" && sessionId && !loading;

  const title = useMemo(() => {
    if (status === "idle") return "准备开始";
    if (status === "active") return `${roleName} 模拟面试`;
    return "面试评价";
  }, [roleName, status]);

  async function handleStart() {
    setLoading(true);
    setError("");
    setEvaluation(null);
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

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content || !canChat) return;

    const nextRoundNo = Math.max(1, ...messages.map((item) => item.roundNo)) + 1;
    setInput("");
    setMessages((current) => [
      ...current,
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
      const result = await sendMessage(sessionId, content);
      setMessages((current) => [
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
      setStatus(result.status === "finished" ? "finished" : "active");
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
      setStatus("idle");
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除会话失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="brand">Interview Agent V1</div>
          <h1>{title}</h1>
        </div>

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
    </main>
  );
}

export default App;
