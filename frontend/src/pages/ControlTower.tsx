import { useNavigate } from "react-router-dom";
import { api, dateBR, money } from "../api";
import { useSession } from "../App";
import { Alert, onListKeys, StatusTag, useLoad } from "../components/ui";

type Task = { client_id: string; client_name: string; severity: string; title: string; detail: string; route: string; count: number; amount: string | null };
type ClientRow = { client_id: string; client_name: string; atrasado: number; hoje: number; concluido: number; valor_atrasado: string; valor_hoje: string; a_classificar: number; a_conciliar: number; integracoes_com_falha: number };
type Connection = { id: string; client_id: string; bank_name: string; conta: string | null; source: string; connection_status: string; last_sync_at: string | null; last_sync_error: string | null };
type Tower = { date: string; totals: Record<string, number>; clients: ClientRow[]; tasks: Task[]; connections: Connection[] };

const WIDGETS: { key: string; status: string; label: string; route: string; hint: string }[] = [
  { key: "atrasado", status: "atrasado", label: "Títulos atrasados", route: "/financeiro?urgency=atrasado", hint: "Vencidos e não liquidados" },
  { key: "hoje", status: "hoje", label: "Vencem hoje", route: "/financeiro?urgency=hoje", hint: "Aprovar, agendar ou liquidar" },
  { key: "concluido", status: "concluido", label: "Liquidados hoje", route: "/financeiro?urgency=concluido", hint: "Baixas do dia" },
  { key: "a_conciliar", status: "hoje", label: "Conciliações sugeridas", route: "/conciliacao", hint: "Confirmar extrato × título" },
  { key: "a_classificar", status: "atencao", label: "Lançamentos sem classificação", route: "/extratos?status=pendente", hint: "Classificar ou aceitar IA" },
  { key: "integracoes_com_falha", status: "erro", label: "Bancos com falha", route: "/extratos", hint: "Reautenticar conexão" },
];

export default function ControlTower() {
  const { setClientId, clients } = useSession();
  const navigate = useNavigate();
  const { data, error, loading } = useLoad<Tower>(() => api("/control-tower"), [clients.length]);
  const open = (route: string, clientId?: string) => {
    if (clientId) setClientId(clientId);
    navigate(route);
  };
  const names = Object.fromEntries((data?.clients ?? []).map((c) => [c.client_id, c.client_name]));

  return (
    <>
      <div className="topbar">
        <h1 tabIndex={-1} className="grow">Torre de controle</h1>
        <span className="muted">Situação de {dateBR(data?.date)} · todas as empresas</span>
      </div>
      <Alert>{error}</Alert>
      {loading && !data && <p className="muted">Carregando…</p>}
      {data && (
        <>
          <section aria-label="Indicadores de status" className="widgets">
            {WIDGETS.map((w) => {
              const n = data.totals[w.key] ?? 0;
              return (
                <button key={w.key} className={`widget ${n ? `w-${w.status}` : "w-zero"}`} onClick={() => open(w.route)}>
                  <span className="widget-n">{n}</span>
                  <span className="widget-label">{w.label}</span>
                  {n > 0 ? <StatusTag kind={w.status} /> : <StatusTag kind="concluido" label="Em dia" />}
                  <span className="muted">{w.hint} →</span>
                </button>
              );
            })}
          </section>

          <div className="tower-grid">
            <section className="card" aria-labelledby="fila">
              <h2 id="fila" style={{ marginTop: 0 }}>Fila de trabalho por criticidade</h2>
              {data.tasks.length === 0 ? <p><StatusTag kind="concluido" label="Nenhuma pendência" /> Tudo em dia.</p> : (
                <ul className="tasks" onKeyDown={onListKeys}>
                  {data.tasks.map((t, i) => (
                    <li key={i}>
                      <button data-row className="task" onClick={() => open(t.route, t.client_id)}>
                        <StatusTag kind={t.severity} />
                        <span className="task-main"><strong>{t.title}</strong><span className="muted">{t.client_name} · {t.detail}</span></span>
                        {t.amount && <span className="num">{money(t.amount)}</span>}
                        <span aria-hidden="true">Resolver →</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="card" aria-labelledby="conexoes">
              <h2 id="conexoes" style={{ marginTop: 0 }}>Integrações bancárias</h2>
              {data.connections.length === 0 && <p className="muted">Nenhuma conta corrente cadastrada.</p>}
              <ul className="plain">
                {data.connections.map((c) => (
                  <li key={c.id}>
                    <StatusTag kind={c.connection_status} />
                    <span><strong>{c.bank_name}</strong> {c.conta && <span className="muted">conta {c.conta}</span>}<br />
                      <span className="muted">{names[c.client_id]} · {c.last_sync_at ? `última sincronização ${new Date(c.last_sync_at + "Z").toLocaleString("pt-BR")}` : "sem sincronização registrada"}</span>
                      {c.last_sync_error && <><br /><span className="field-error">{c.last_sync_error}</span></>}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section className="card" aria-labelledby="empresas">
            <h2 id="empresas" style={{ marginTop: 0 }}>Empresas</h2>
            <table onKeyDown={onListKeys}>
              <thead><tr><th>Empresa</th><th>Atrasados</th><th>Para hoje</th><th>Concluídos hoje</th><th>A conciliar</th><th>A classificar</th><th /></tr></thead>
              <tbody>
                {data.clients.map((c) => (
                  <tr key={c.client_id}>
                    <td><strong>{c.client_name}</strong></td>
                    <td>{c.atrasado ? <StatusTag kind="atrasado" count={c.atrasado} label={money(c.valor_atrasado)} /> : "—"}</td>
                    <td>{c.hoje ? <StatusTag kind="hoje" count={c.hoje} label={money(c.valor_hoje)} /> : "—"}</td>
                    <td>{c.concluido ? <StatusTag kind="concluido" count={c.concluido} label="" /> : "—"}</td>
                    <td>{c.a_conciliar || "—"}</td>
                    <td>{c.a_classificar || "—"}</td>
                    <td><button data-row className="secondary" onClick={() => open("/financeiro", c.client_id)}>Abrir empresa</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}
