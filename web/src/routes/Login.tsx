import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export function Login() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/shipments" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signIn(email.trim().toLowerCase(), password);
      const target = (location.state as { from?: string } | null)?.from ?? "/shipments";
      navigate(target, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not sign in. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function fill(kind: "exec" | "manager") {
    setEmail(`${kind}@demo.local`);
    setPassword(kind === "exec" ? "demo-exec-2026" : "demo-manager-2026");
    setError(null);
  }

  return (
    <div className="login">
      <section className="login-brand">
        <div>
          <div className="brand">
            <div className="brand-mark">
              <Icon name="box" size={16} />
            </div>
            <div className="brand-name">
              Customs<span>-AI</span>
            </div>
          </div>
        </div>

        <div>
          <h1 className="login-headline">
            Every shipment <em>checked</em> before it files.
          </h1>
          <p className="login-sub">
            Drop in the invoice, packing list and bill of lading. Get structured data with
            evidence, contradictions surfaced, and nothing exported until a person has cleared it.
          </p>

          <div className="login-points">
            <div className="login-point">
              <Icon name="check" size={15} />
              <span>Every field carries the quote and page it came from.</span>
            </div>
            <div className="login-point">
              <Icon name="check" size={15} />
              <span>Quantities, packages and weights reconciled across all three documents.</span>
            </div>
            <div className="login-point">
              <Icon name="check" size={15} />
              <span>Executive reviews, manager approves, every change is attributed.</span>
            </div>
          </div>
        </div>

        <p className="login-legal">
          Demo environment with synthetic documents only. No client data is stored.
        </p>
      </section>

      <section className="login-form-wrap">
        <div className="login-card">
          <h1>Sign in</h1>
          <p className="sub">Use your documentation workspace account.</p>

          <form onSubmit={submit}>
            <div className="field">
              <label className="label" htmlFor="email">
                Work email
              </label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="username"
                placeholder="you@company.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <div className="field">
              <label className="label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••••••"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            {error && (
              <div className="form-error" role="alert">
                <Icon name="alert" size={15} />
                <span>{error}</span>
              </div>
            )}

            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? <Icon name="refresh" size={15} className="spin" /> : null}
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="demo-box">
            <div className="title">Demo access</div>
            <div className="demo-buttons">
              <button type="button" className="btn" onClick={() => fill("exec")}>
                <Icon name="user" size={14} />
                Executive
              </button>
              <button type="button" className="btn" onClick={() => fill("manager")}>
                <Icon name="check" size={14} />
                Manager
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
