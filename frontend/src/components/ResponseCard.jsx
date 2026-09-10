import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import RateLimitNotice from "./RateLimitNotice";

const ICONS = {
  ollama: { bg: "#f97316", label: "🦙" },
  mistral: { bg: "#f59e0b", label: "M" },
  gemini: { bg: "#4285f4", label: "✦" },
  openai: { bg: "#10a37f", label: "◎" },
};

function getIcon(modelId) {
  const kind = modelId.split(":")[0];
  return ICONS[kind] || { bg: "#6b7280", label: kind[0]?.toUpperCase() || "?" };
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button className="icon-btn" onClick={copy} title="Copy">
      {copied ? "✓" : "⧉"}
    </button>
  );
}

function ResponseCard({ modelId, data }) {
  if (!data) return null;
  const {
    display_name,
    text,
    done,
    error,
    retry_after,
    latency_ms,
    score,
    verdict,
    is_winner,
  } = data;

  const icon = getIcon(modelId);
  const isRateLimit = Boolean(retry_after);

  return (
    <article className={`model-column${is_winner ? " winner" : ""}`}>
      <div className="model-header">
        <div className="model-icon" style={{ background: icon.bg }}>
          {icon.label}
        </div>
        <div className="model-meta">
          <h3>{display_name}</h3>
          <span>{modelId}</span>
        </div>
        {is_winner && <span className="winner-badge">🏆 Best</span>}
        {text && <CopyButton text={text} />}
      </div>

      <div className="model-body">
        {error ? (
          isRateLimit ? (
            <RateLimitNotice retryAfter={retry_after} />
          ) : (
            <p className="error-text">⚠ {error}</p>
          )
        ) : text ? (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        ) : done ? (
          <p className="muted">(empty response)</p>
        ) : (
          <div className="gen-indicator">
            <span className="dots">
              <span />
              <span />
              <span />
            </span>
            <span>Generating response…</span>
          </div>
        )}
      </div>

      <div className="model-footer">
        {typeof score === "number" && <span className="chip">Score {score}</span>}
        {latency_ms != null && done && (
          <span className="chip">{(latency_ms / 1000).toFixed(1)}s</span>
        )}
      </div>
    </article>
  );
}

export default ResponseCard;