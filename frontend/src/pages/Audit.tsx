import { useState } from "react";
import { api } from "../api";
import { Alert, useLoad } from "../components/ui";

type Entry = { id: number; at: string; user_id: string | null; ip: string | null; action: string; entity: string; entity_id: string | null; changes: Record<string, unknown> | null };
type U = { id: string; name: string };

export default function AuditPage() {
  const [entity, setEntity] = useState("");
  const log = useLoad<Entry[]>(() => api(`/audit${entity ? `?entity=${entity}` : ""}`), [entity]);
  const users = useLoad<U[]>(() => api("/users"), []);
  const who = (id: string | null) => users.data?.find((u) => u.id === id)?.name ?? (id ? id.slice(0, 8) : "sistema");

  return (
    <>
      <div className="topbar">
        <h1 tabIndex={-1} className="grow">Trilha de auditoria</h1>
        <select value={entity} onChange={(e) => setEntity(e.target.value)} aria-label="Entidade">
          <option value="">Todas as entidades</option>
          {["users", "clients", "contracts", "terms", "term_acceptances", "documents", "invoices", "invoice_items",
            "titles", "reconciliations", "bank_transactions", "investment_statements", "powers_of_attorney", "chart_accounts", "api_keys", "offices"].map((e) => <option key={e}>{e}</option>)}
        </select>
      </div>
      <Alert>{log.error}</Alert>
      <div className="card">
        <table>
          <thead><tr><th>Quando</th><th>Quem</th><th>IP</th><th>Ação</th><th>Entidade</th><th>O que mudou</th></tr></thead>
          <tbody>
            {log.data?.map((e) => (
              <tr key={e.id}>
                <td>{new Date(e.at + "Z").toLocaleString("pt-BR")}</td><td>{who(e.user_id)}</td><td>{e.ip ?? "—"}</td>
                <td><span className="badge">{e.action}</span></td><td>{e.entity}<div className="muted">{e.entity_id?.slice(0, 8)}</div></td>
                <td style={{ whiteSpace: "normal", maxWidth: 480 }}>
                  <code style={{ fontSize: ".75rem" }}>{e.changes ? JSON.stringify(e.changes).slice(0, 400) : ""}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
