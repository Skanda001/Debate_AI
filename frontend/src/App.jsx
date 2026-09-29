import { useEffect, useRef, useState } from "react";
import "./App.css";
import ResponseCard from "./components/ResponseCard";
import JudgePanel from "./components/JudgePanel";
import HistoryDrawer from "./components/HistoryDrawer";
import AuthModal from "./components/AuthModal";
import { MODES, buildPrompt } from "./modes";
import {
  streamAsk,
  fetchHistory,
  fetchDetail,
  deleteQuestion,
  clearHistory,
  togglePin,
  apiGetMe,
  apiLogout,
} from "./api";

function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [activeQuestionId, setActiveQuestionId] = useState(null);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("direct");
  const [asking, setAsking] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [responses, setResponses] = useState({});
  const [judge, setJudge] = useState(null);
  const [judging, setJudging] = useState(false);
  const [evaluations, setEvaluations] = useState([]);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const esRef = useRef(null);
  const taRef = useRef(null);

  const displayComparison = (data) => {
    if (data?.id) setActiveQuestionId(data.id);
    setCurrentQuestion(data.text);
    const respMap = {};
    (data.responses || []).forEach((r) => {
      respMap[r.model_id] = {
        display_name: r.display_name,
        text: r.response,
        done: true,
        error: r.error,
        retry_after: r.retry_after,
        latency_ms: r.latency_ms,
        score: r.score,
        verdict: r.verdict,
        is_winner: r.is_winner,
      };
    });
    setResponses(respMap);
    setJudge(data.judgment);
    setEvaluations(data.judgment?.evaluations || []);
    setJudging(false);
    setAsking(false);
  };

  const loadHistory = async () => {
    try {
      const data = await fetchHistory();
      const list = Array.isArray(data) ? data : [];
      setHistory(list);
      return list;
    } catch (e) {
      console.error(e);
      setHistory([]);
      return [];
    }
  };

  useEffect(() => {
    const init = async () => {
      const me = await apiGetMe();
      if (me) {
        setCurrentUser(me);
      }
      const items = await loadHistory();
      const savedId = localStorage.getItem("debate_ai_active_id");
      if (savedId && savedId !== "none") {
        await openFromHistory(savedId, false);
      } else if (!savedId && items && items.length > 0) {
        await openFromHistory(items[0].id, false);
      }
    };
    init();
    return () => esRef.current?.close();
  }, []);

  const reset = () => {
    setResponses({});
    setJudge(null);
    setJudging(false);
    setEvaluations([]);
    setConnectionError("");
  };

  const ask = () => {
    const q = question.trim();
    if (!q || asking) return;

    const finalPrompt = buildPrompt(q, mode);
    reset();
    setCurrentQuestion(q);
    setAsking(true);
    setQuestion("");

    const parentId = activeQuestionId;
    const es = streamAsk(finalPrompt, {
      start: (data) => {
        if (data.models && Array.isArray(data.models)) {
          const initial = {};
          data.models.forEach((m) => {
            initial[m.model_id] = {
              display_name: m.display_name,
              text: "",
              done: false,
              error: null,
            };
          });
          setResponses(initial);
        }
      },
      model_started: (data) => {
        setResponses((prev) => ({
          ...prev,
          [data.model_id]: {
            ...(prev[data.model_id] || {}),
            display_name: data.display_name,
            text: prev[data.model_id]?.text || "",
            done: false,
            error: null,
          },
        }));
      },
      model_chunk: (data) => {
        setResponses((prev) => {
          const existing = prev[data.model_id] || { text: "" };
          return {
            ...prev,
            [data.model_id]: { ...existing, text: existing.text + data.chunk },
          };
        });
      },
      model_finished: (data) => {
        setResponses((prev) => ({
          ...prev,
          [data.model_id]: {
            ...prev[data.model_id],
            text: data.response,
            done: true,
            error: data.error,
            retry_after: data.retry_after,
            latency_ms: data.latency_ms,
          },
        }));
      },
      judge_started: () => setJudging(true),
      complete: (data) => {
        const result = data.result;
        displayComparison(result);
        localStorage.setItem("debate_ai_active_id", result.id);
        loadHistory();
        esRef.current?.close();
      },
      error: (data) => {
        setConnectionError(data?.message || "Something went wrong.");
        setAsking(false);
        setJudging(false);
        esRef.current?.close();
      },
    }, parentId);
    esRef.current = es;
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  };

  const openFromHistory = async (id, scrollToTop = true) => {
    try {
      const data = await fetchDetail(id);
      if (data && data.text) {
        displayComparison(data);
        localStorage.setItem("debate_ai_active_id", id);
        setShowHistory(false);
        if (scrollToTop) {
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      }
    } catch (e) {
      console.error("Failed to load comparison", e);
    }
  };

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    await deleteQuestion(id);
    const savedId = localStorage.getItem("debate_ai_active_id");
    if (String(savedId) === String(id)) {
      newComparison();
    }
    loadHistory();
  };

  const handleClear = async () => {
    await clearHistory();
    newComparison();
    loadHistory();
  };

  const handlePin = async (id, e) => {
    e.stopPropagation();
    await togglePin(id);
    loadHistory();
  };

  const newComparison = () => {
    setQuestion("");
    setCurrentQuestion("");
    setActiveQuestionId(null);
    reset();
    localStorage.setItem("debate_ai_active_id", "none");
    taRef.current?.focus();
  };

  const stopGenerating = () => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setAsking(false);
    setJudging(false);
    setResponses((prev) => {
      const updated = { ...prev };
      Object.keys(updated).forEach((id) => {
        if (!updated[id].done) {
          updated[id] = {
            ...updated[id],
            done: true,
            text: (updated[id].text || "") + (updated[id].text ? " … [stopped]" : "[Stopped by user]"),
          };
        }
      });
      return updated;
    });
    taRef.current?.focus();
  };

  const handleAuthSuccess = async (user) => {
    setCurrentUser(user);
    const items = await loadHistory();
    if (items && items.length > 0) {
      await openFromHistory(items[0].id, false);
    } else {
      newComparison();
    }
  };

  const handleLogout = async () => {
    await apiLogout();
    setCurrentUser(null);
    newComparison();
    await loadHistory();
  };

  const modelIds = Object.keys(responses);
  const hasActive = modelIds.length > 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-pill">DEBATE AI</span>
          <h1>Compare AI answers, side by side</h1>
          <p>
            Ask one question. Watch several models answer live, then see which
            one wins.
          </p>
        </div>
        <div className="top-actions">
          <button className="ghost-btn" onClick={newComparison}>
            New
          </button>
          <button className="ghost-btn" onClick={() => setShowHistory(true)}>
            History
          </button>

          {currentUser ? (
            <div className="user-badge-wrap" title={`Logged in as ${currentUser.username}`}>
              <span className="user-avatar-circle">
                {currentUser.username.charAt(0).toUpperCase()}
              </span>
              <span className="user-name-text">{currentUser.username}</span>
              <button className="user-logout-btn" onClick={handleLogout} title="Log Out">
                Log Out
              </button>
            </div>
          ) : (
            <button className="ghost-btn auth-ghost-btn" onClick={() => setShowAuthModal(true)}>
              <span>👤</span> Sign In
            </button>
          )}
        </div>
      </header>

      <div className="mode-bar">
        {MODES.map((m) => (
          <button
            key={m.id}
            className={`mode-chip${mode === m.id ? " active" : ""}`}
            onClick={() => setMode(m.id)}
            type="button"
          >
            <span>{m.icon}</span> {m.label}
          </button>
        ))}
      </div>

      {connectionError && <p className="connection-error">{connectionError}</p>}

      {currentQuestion && (
        <div className="active-question">
          <div className="active-question-header">
            <span>Question</span>
            {(asking || judging) && (
              <button
                type="button"
                className="stop-mini-btn"
                onClick={stopGenerating}
                title="Stop generation"
              >
                <span className="stop-square">■</span> Stop
              </button>
            )}
          </div>
          <h2>{currentQuestion}</h2>
        </div>
      )}

      {hasActive && (
        <section
          className="comparison-grid"
          data-count={Math.min(modelIds.length, 4)}
        >
          {modelIds.map((id) => (
            <ResponseCard key={id} modelId={id} data={responses[id]} />
          ))}
        </section>
      )}

      {(judging || judge) && (
        <JudgePanel judge={judge} judging={judging} evaluations={evaluations} />
      )}

      {!hasActive && !asking && !connectionError && (
        <div className="empty-state">
          <h2>No comparison yet</h2>
          <p>
            Pick a mode above, ask a question below, and watch the models race.
          </p>
        </div>
      )}

      <div className="prompt-dock">
        <div className="prompt-inner">
          <textarea
            ref={taRef}
            placeholder="Ask me anything…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={asking}
            rows={1}
          />
          <div className="prompt-actions">
            <div className="prompt-actions-left">
              <button className="mini-btn" type="button" title="Mode">
                {MODES.find((m) => m.id === mode)?.icon}{" "}
                {MODES.find((m) => m.id === mode)?.label}
              </button>
              {activeQuestionId && currentQuestion && (
                <span className="thread-pill" title={`Follow-up with history context: "${currentQuestion}"`}>
                  <span>🔗 Thread Active</span>
                  <button
                    type="button"
                    className="thread-detach-btn"
                    onClick={() => setActiveQuestionId(null)}
                    title="Detach and ask without conversation history"
                  >
                    ×
                  </button>
                </span>
              )}
            </div>
            <div className="prompt-actions-right">
              {asking || judging ? (
                <button
                  type="button"
                  className="stop-btn"
                  onClick={stopGenerating}
                  title="Stop generating"
                >
                  <span className="stop-square">■</span> Stop
                </button>
              ) : (
                <button
                  type="button"
                  className="send-btn"
                  onClick={ask}
                  disabled={!question.trim()}
                  title="Send"
                >
                  ➤
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {showHistory && (
        <HistoryDrawer
          history={history}
          currentUser={currentUser}
          onOpenAuth={() => setShowAuthModal(true)}
          onClose={() => setShowHistory(false)}
          onOpen={openFromHistory}
          onDelete={handleDelete}
          onClear={handleClear}
          onPin={handlePin}
        />
      )}

      <AuthModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        onSuccess={handleAuthSuccess}
      />
    </div>
  );
}

export default App;
