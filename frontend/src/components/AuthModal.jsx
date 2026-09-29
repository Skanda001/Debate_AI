import { useState } from "react";
import { apiLogin, apiRegister } from "../api";

export default function AuthModal({ isOpen, onClose, onSuccess }) {
  const [isSignUp, setIsSignUp] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    const u = username.trim();
    const p = password.trim();
    const em = email.trim();

    if (!u) {
      setError("Please enter your username.");
      return;
    }
    if (!p) {
      setError("Please enter your password.");
      return;
    }
    if (isSignUp && p.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);
    try {
      let data;
      if (isSignUp) {
        data = await apiRegister(u, em, p);
      } else {
        data = await apiLogin(u, p);
      }
      onSuccess(data.user);
      onClose();
    } catch (err) {
      setError(err.message || "Authentication failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (signUp) => {
    setIsSignUp(signUp);
    setError("");
  };

  return (
    <div className="auth-modal-overlay" onClick={onClose}>
      <div className="auth-modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="auth-close-btn" onClick={onClose} aria-label="Close modal">
          ×
        </button>

        <div className="auth-header">
          <div className="auth-badge">DEBATE AI ACCOUNT</div>
          <h2>{isSignUp ? "Create an account" : "Welcome back"}</h2>
          <p>
            {isSignUp
              ? "Save all your model debates and personal chat history permanently."
              : "Sign in to access your saved comparisons across all devices."}
          </p>
        </div>

        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${!isSignUp ? "active" : ""}`}
            onClick={() => switchMode(false)}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab ${isSignUp ? "active" : ""}`}
            onClick={() => switchMode(true)}
          >
            Sign Up
          </button>
        </div>

        {error && <div className="auth-error-banner">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="auth-username">
              Username {isSignUp ? "" : "or Email"}
            </label>
            <input
              id="auth-username"
              type="text"
              autoFocus
              placeholder={isSignUp ? "e.g. alex_coder" : "Your username or email"}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoComplete="username"
            />
          </div>

          {isSignUp && (
            <div className="auth-field">
              <label htmlFor="auth-email">Email (optional)</label>
              <input
                id="auth-email"
                type="email"
                placeholder="alex@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
                autoComplete="email"
              />
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              placeholder={isSignUp ? "At least 6 characters" : "••••••••"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete={isSignUp ? "new-password" : "current-password"}
            />
          </div>

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <span className="auth-spinner-label">Please wait…</span>
            ) : isSignUp ? (
              "Create Account"
            ) : (
              "Sign In"
            )}
          </button>
        </form>

        <div className="auth-footer-note">
          {isSignUp ? (
            <span>
              Already have an account?{" "}
              <button
                type="button"
                className="auth-link-btn"
                onClick={() => switchMode(false)}
              >
                Sign In
              </button>
            </span>
          ) : (
            <span>
              Don't have an account yet?{" "}
              <button
                type="button"
                className="auth-link-btn"
                onClick={() => switchMode(true)}
              >
                Sign Up
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
