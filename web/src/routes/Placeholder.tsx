import { useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";

export function Placeholder({
  title,
  description,
  phase,
}: {
  title: string;
  description: string;
  phase: string;
}) {
  const navigate = useNavigate();
  return (
    <div className="page page-enter" style={{ maxWidth: 760 }}>
      <div className="card" style={{ padding: 30 }}>
        <div className="empty-icon">
          <Icon name="box" size={19} />
        </div>
        <h1 style={{ fontSize: 20, fontWeight: 600, marginTop: 8 }}>{title}</h1>
        <p style={{ color: "var(--muted)", marginTop: 6, maxWidth: 520 }}>{description}</p>
        <p style={{ color: "var(--faint)", marginTop: 18, fontSize: 12 }}>{phase}</p>
        <button className="btn btn-sm" type="button" style={{ marginTop: 16 }} onClick={() => navigate("/shipments")}>
          <Icon name="arrow-left" size={14} />
          Back to shipments
        </button>
      </div>
    </div>
  );
}
