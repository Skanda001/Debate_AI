function ScoreBar({ score }) {
  if (score == null) return null;
  const pct = Math.max(0, Math.min(100, score));
  const color = pct >= 70 ? "#22c55e" : pct >= 40 ? "#eab308" : "#f87171";
  return (
    <div className="score-bar-wrap">
      <div className="score-bar" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

function JudgePanel({ judge, judging, evaluations }) {
  return (
    <section className="judge-panel">
      <div className="judge-header">
        <span className="judge-label">Independent Arbiter</span>
        <h2>{judging ? "Comparing answers…" : "Judge Verdict"}</h2>
      </div>

      {judging && !judge && (
        <p className="judging-text">Reading every candidate answer, checking facts, and scoring models now…</p>
      )}

      {judge && (
        <>
          <div className="judge-main-verdict">
            <div className="judge-verdict-title">
              <span className="verdict-trophy">🏆</span>
              <h3>Why the Winner Won</h3>
            </div>
            <p className="judge-reason">{judge.reason}</p>
          </div>

          {judge.why_others_lost && (
            <div className="judge-why-others-card">
              <div className="why-others-header">
                <span className="why-others-icon">🔍</span>
                <h4>Why the Other Models Fell Short</h4>
              </div>
              <p className="why-others-text">{judge.why_others_lost}</p>
            </div>
          )}

          {judge.consensus && (
            <p className="judge-consensus">
              <strong>Consensus: </strong>
              {judge.consensus}
            </p>
          )}

          {evaluations && evaluations.length > 0 && (
            <div className="eval-list">
              <h4 className="eval-list-title">Detailed Model Breakdown</h4>
              {evaluations.map((e) => {
                const isWinner = e.model === judge.winner_model_id;
                return (
                  <div className={`eval-row${isWinner ? " winner-eval" : ""}`} key={e.model}>
                    <div className="eval-head">
                      <div className="eval-model-name">
                        {isWinner && <span className="eval-winner-tag">Winner</span>}
                        <span>{e.display_name || e.model}</span>
                      </div>
                      <span className="eval-score">{e.score != null ? `${e.score}/100` : "—"}</span>
                    </div>

                    <ScoreBar score={e.score} />

                    {e.verdict && <p className="eval-verdict">{e.verdict}</p>}

                    {e.why_not_winner && !isWinner && (
                      <div className="eval-why-not-box">
                        <span className="why-not-tag">Why not winner:</span>
                        <span className="why-not-text">{e.why_not_winner}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default JudgePanel;