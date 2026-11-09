import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { api, ApiError } from "../lib/api";

const INCOTERMS = ["FOB", "CIF", "CFR", "EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"];
const CURRENCIES = ["USD", "EUR", "GBP", "CNY", "INR", "AED", "JPY"];

export function NewShipment() {
  const navigate = useNavigate();
  const [ref, setRef] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [incoterm, setIncoterm] = useState("FOB");
  const [error, setError] = useState<string | null>(null);

  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: api.suppliers });

  useEffect(() => {
    const next = `SHP-${String(Math.floor(24820 + Math.random() * 79))}`;
    setRef(next);
  }, []);

  const create = useMutation({
    mutationFn: () =>
      api.createShipment({
        ref,
        supplier_id: supplierId || null,
        currency,
        incoterm,
      }),
    onSuccess: (shipment) => navigate(`/shipments/${shipment.id}`),
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not create shipment."),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    create.mutate();
  }

  return (
    <div className="page page-enter" style={{ maxWidth: 720 }}>
      <button className="btn btn-ghost btn-sm" type="button" onClick={() => navigate(-1)}>
        <Icon name="arrow-left" size={14} />
        Back
      </button>

      <div className="page-head" style={{ marginTop: 14 }}>
        <div>
          <h1>New shipment</h1>
          <p className="sub">
            Create the record first. Documents can be added now or as they arrive.
          </p>
        </div>
      </div>

      <form className="card" onSubmit={submit}>
        <div style={{ padding: 22, display: "grid", gap: 18 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="field">
              <label className="label" htmlFor="ref">
                Shipment reference
              </label>
              <input
                id="ref"
                className="input num"
                value={ref}
                onChange={(event) => setRef(event.target.value.toUpperCase())}
                placeholder="SHP-25001"
                required
              />
            </div>

            <div className="field">
              <label className="label" htmlFor="supplier">
                Supplier
              </label>
              <select
                id="supplier"
                className="select"
                value={supplierId}
                onChange={(event) => setSupplierId(event.target.value)}
              >
                <option value="">Select supplier</option>
                {suppliers.data?.map((supplier) => (
                  <option key={supplier.id} value={supplier.id}>
                    {supplier.name}
                    {supplier.country_code ? ` (${supplier.country_code})` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="label" htmlFor="currency">
                Invoice currency
              </label>
              <select
                id="currency"
                className="select"
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
              >
                {CURRENCIES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="label" htmlFor="incoterm">
                Incoterm
              </label>
              <select
                id="incoterm"
                className="select"
                value={incoterm}
                onChange={(event) => setIncoterm(event.target.value)}
              >
                {INCOTERMS.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <div className="form-error" role="alert">
              <Icon name="alert" size={15} />
              <span>{error}</span>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button className="btn" type="button" onClick={() => navigate("/shipments")}>
              Cancel
            </button>
            <button className="btn btn-primary" type="submit" disabled={create.isPending || !ref}>
              {create.isPending ? (
                <Icon name="refresh" size={15} className="spin" />
              ) : (
                <Icon name="arrow-right" size={15} />
              )}
              Create shipment
            </button>
          </div>
        </div>
      </form>

      <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 12 }}>
        Shipment references are unique per organisation. A duplicate returns a clear conflict
        instead of creating a second record.
      </p>
    </div>
  );
}
