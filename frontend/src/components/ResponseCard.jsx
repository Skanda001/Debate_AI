function ResponseCard({ modelId, data }) {
  if (!data) return null;
  const { display_name, text, done, error, latency_ms, score, verdict, is_winner } = data;

  return (
    <article className={`response-card${is_winner ? " winner" : ""}`}>
      <div className="response-card-header">
        <div className="response-card-title">
          <h3>{display_name}</h3>
          <span className="model-id">{modelId}</span>
        </div>
        {is_winner && <span className="winner-badge">Best answer</span>}
      </div>

      <div className="response-body">
        {error ? (
          <p className="error-text">Error: {error}</p>
        ) : (
          <p>{text || (done ? "(empty response)" : "")}</p>
        )}
        {!done && !error && <span className="typing-dot" aria-label="generating" />}
      </div>

      <div className="response-footer">
        {typeof score === "number" && <span className="score-chip">Score {score}</span>}
        {latency_ms != null && done && <span className="latency-chip">{latency_ms} ms</span>}
      </div>

      {verdict && <p className="verdict-text">{verdict}</p>}
    </article>
  );
}

export default ResponseCard;
