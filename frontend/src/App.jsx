import { useEffect, useRef, useState } from "react";
import "./App.css";
import ResponseCard from "./components/ResponseCard";
import JudgePanel from "./components/JudgePanel";
import HistoryDrawer from "./components/HistoryDrawer";
import { streamAsk, fetchHistory, fetchDetail, deleteQuestion, clearHistory, togglePin } from "./api";

function App() {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [responses, setResponses] = useState({}); // model_id -> {display_name, text, done, error, ...}
  const [judge, setJudge] = useState(null);
  const [judging, setJudging] = useState(false);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const esRef = useRef(null);

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
    setConnectionError("");
  };

  const handleAsk = (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || asking) return;

    reset();
    setCurrentQuestion(q);
    setAsking(true);
    setQuestion("");

    const es = streamAsk(q, {
      model_started: (data) => {
        setResponses((prev) => ({
          ...prev,
          [data.model_id]: { display_name: data.display_name, text: "", done: false, error: null },
        }));
      },
      model_chunk: (data) => {
        setResponses((prev) => {
          const existing = prev[data.model_id] || { text: "" };
          return { ...prev, [data.model_id]: { ...existing, text: existing.text + data.chunk } };
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
            latency_ms: r.latency_ms,
            score: r.score,
            verdict: r.verdict,
            is_winner: r.is_winner,
          };
        });
        setResponses(respMap);
        setJudge(result.judgment);
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
        latency_ms: r.latency_ms,
        score: r.score,
        verdict: r.verdict,
        is_winner: r.is_winner,
      };
    });
    setResponses(respMap);
    setJudge(data.judgment);
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
  };

  const modelIds = Object.keys(responses);
  const hasActive = modelIds.length > 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-pill">LLM Arena</span>
          <h1>Compare AI answers, side by side</h1>
          <p>Ask one question. Watch several models answer live, then see which one wins and why.</p>
        </div>
        <div className="top-actions">
          <button className="ghost-btn" onClick={newComparison}>New</button>
          <button className="ghost-btn" onClick={() => setShowHistory(true)}>History</button>
        </div>
      </header>

      <form className="prompt-bar" onSubmit={handleAsk}>
        <textarea
          placeholder="Ask anything… e.g. Explain quantum entanglement simply"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={asking}
          rows={3}
        />
        <button type="submit" disabled={asking || !question.trim()}>
          {asking ? "Comparing…" : "Compare answers"}
        </button>
      </form>

      {connectionError && <p className="connection-error">{connectionError}</p>}

      {currentQuestion && (
        <div className="active-question">
          <span>Question</span>
          <h2>{currentQuestion}</h2>
        </div>
      )}

      {hasActive && (
        <section
          className="response-grid"
          style={{ gridTemplateColumns: `repeat(${Math.min(modelIds.length, 3)}, minmax(0, 1fr))` }}
        >
          {modelIds.map((id) => (
            <ResponseCard key={id} modelId={id} data={responses[id]} />
          ))}
        </section>
      )}

      {(judging || judge) && <JudgePanel judge={judge} judging={judging} />}

      {!hasActive && !asking && !connectionError && (
        <div className="empty-state">
          <h2>No comparison yet</h2>
          <p>Ask a question above, or open a saved comparison from history.</p>
        </div>
      )}

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
