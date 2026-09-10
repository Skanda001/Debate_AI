import { useEffect, useRef, useState } from "react";
import "./App.css";
import ResponseCard from "./components/ResponseCard";
import JudgePanel from "./components/JudgePanel";
import HistoryDrawer from "./components/HistoryDrawer";
import { MODES, buildPrompt } from "./modes";
import {
  streamAsk,
  fetchHistory,
  fetchDetail,
  deleteQuestion,
  clearHistory,
  togglePin,
} from "./api";

function App() {
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

  const loadHistory = async () => {
    try {
      setHistory(await fetchHistory());
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadHistory();
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
        const respMap = {};
        result.responses.forEach((r) => {
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
        setJudge(result.judgment);
        setEvaluations(result.judgment?.evaluations || []);
        setJudging(false);
        setAsking(false);
        loadHistory();
        esRef.current?.close();
      },
      error: (data) => {
        setConnectionError(data?.message || "Something went wrong.");
        setAsking(false);
        setJudging(false);
        esRef.current?.close();
      },
    });
    esRef.current = es;
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  };

  const openFromHistory = async (id) => {
    const data = await fetchDetail(id);
    setCurrentQuestion(data.text);
    const respMap = {};
    data.responses.forEach((r) => {
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
    setShowHistory(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    await deleteQuestion(id);
    loadHistory();
  };
  const handleClear = async () => {
    await clearHistory();
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
    reset();
    taRef.current?.focus();
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
          <span>Question</span>
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
            </div>
            <button
              className="send-btn"
              onClick={ask}
              disabled={asking || !question.trim()}
              title="Send"
            >
              {asking ? "…" : "➤"}
            </button>
          </div>
        </div>
      </div>

      {showHistory && (
        <HistoryDrawer
          history={history}
          onClose={() => setShowHistory(false)}
          onOpen={openFromHistory}
          onDelete={handleDelete}
          onClear={handleClear}
          onPin={handlePin}
        />
      )}
    </div>
  );
}

export default App;
