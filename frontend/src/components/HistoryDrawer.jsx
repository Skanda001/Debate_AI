function HistoryDrawer({ history, onClose, onOpen, onDelete, onClear, onPin }) {
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <h2>History</h2>
            <p>{history.length} saved comparisons</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>

        <button className="clear-btn" onClick={onClear} disabled={history.length === 0}>
          Clear all
        </button>

        <div className="drawer-list">
          {history.length === 0 && <p className="muted">No comparisons yet.</p>}

          {history.map((item) => {
            const winner = item.responses?.find((r) => r.is_winner);
            return (
              <div className="drawer-item" key={item.id} onClick={() => onOpen(item.id)}>
                <h4>
                  {item.is_pinned && <span className="pin-tag">Pinned</span>}
                  {item.text}
                </h4>
                <p>
                  {new Date(item.created_at).toLocaleString()} • {item.responses?.length || 0} models
                  {winner && <> • won by <strong>{winner.display_name}</strong></>}
                </p>
                <div className="drawer-item-actions">
                  <button onClick={(e) => onPin(item.id, e)}>{item.is_pinned ? "Unpin" : "Pin"}</button>
                  <button className="danger" onClick={(e) => onDelete(item.id, e)}>Delete</button>
                </div>
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
}

export default HistoryDrawer;
