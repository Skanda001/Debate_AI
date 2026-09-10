function JudgePanel({ judge, judging }) {
  return (
    <section className="judge-panel">
      <div className="judge-header">
        <span className="judge-label">Judge</span>
        <h2>{judging ? "Comparing answers…" : "Verdict"}</h2>
      </div>

      {judging && !judge && <p className="judging-text">Reading every answer and scoring them now.</p>}

      {judge && (
        <>
          <p className="judge-reason">{judge.reason}</p>
          <p className="judge-consensus">
            <strong>Agreement between models: </strong>
            {judge.consensus}
          </p>
        </>
      )}
    </section>
  );
}

export default JudgePanel;
