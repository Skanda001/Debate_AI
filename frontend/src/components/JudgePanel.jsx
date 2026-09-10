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
        <span className="judge-label">Judge</span>
        <h2>{judging ? "Comparing answers…" : "Verdict"}</h2>
      </div>

      {judging && !judge && (
        <p className="judging-text">Reading every answer and scoring them now…</p>
      )}

      {judge && (
        <>
          <p className="judge-reason">{judge.reason}</p>
          <p className="judge-consensus">
            <strong>Agreement: </strong>
            {judge.consensus}
          </p>

          {evaluations && evaluations.length > 0 && (
            <div className="eval-list">
              {evaluations.map((e) => (
                <div className="eval-row" key={e.model}>
                  <div className="eval-head">
                    <span className="eval-model">{e.model}</span>
                    <span className="eval-score">{e.score ?? "—"}</span>
                  </div>
                  <ScoreBar score={e.score} />
                  {e.verdict && <p className="eval-verdict">{e.verdict}</p>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default JudgePanel;