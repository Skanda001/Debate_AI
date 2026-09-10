import { useEffect, useState } from "react";

function formatWait(seconds) {
  if (seconds <= 0) return "now";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  const min = m % 60;
  return `${h}h ${min}m`;
}

function clockTime(seconds) {
  const d = new Date(Date.now() + seconds * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function RateLimitNotice({ retryAfter }) {
  const [left, setLeft] = useState(retryAfter ?? 0);

  useEffect(() => {
    if (!retryAfter || retryAfter <= 0) return;
    setLeft(retryAfter);
    const t = setInterval(() => {
      setLeft((v) => (v > 0 ? v - 1 : 0));
    }, 1000);
    return () => clearInterval(t);
  }, [retryAfter]);

  if (!retryAfter || retryAfter <= 0) return null;

  if (left <= 0) {
    return (
      <div className="rate-limit-notice ready">
        ✅ Limit reset — you can try again now.
      </div>
    );
  }

  const resetsAt = clockTime(left);

  return (
    <div className="rate-limit-notice">
      🚫 <strong>Daily limit reached.</strong> Try again in{" "}
      <strong>{formatWait(left)}</strong> (around {resetsAt}).
    </div>
  );
}