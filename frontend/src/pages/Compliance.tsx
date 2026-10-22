import { Fragment, FormEvent, useState } from "react";
import { api, dateBR, money, post } from "../api";
import { useSession } from "../App";
import { Alert, useLoad } from "../components/ui";

type Contract = { id: string; client_id: string; content: string; content_sha256: string; monthly_fee: string; start_date: string; status: string; accepted_at: string | null; accepted_ip: string | null };
type Term = { id: string; kind: string; version: number; title: string; body: string };
type Poa = { id: string; outorgante: string; outorgado: string; finalidade: string; orgao: string | null; valid_from: string; valid_until: string | null; revoked_at: string | null };

export default function CompliancePage() {
  const { clientId, user } = useSession();
  const staff = user.role !== "cliente";
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const contracts = useLoad<Contract[]>(() => api(`/contracts${staff && clientId ? `?client_id=${clientId}` : ""}`), [clientId]);
  const pending = useLoad<Term[]>(() => api("/terms/pending"), []);
  const terms = useLoad<Term[]>(() => api("/terms"), []);
  const poas = useLoad<Poa[]>(() => api(`/powers-of-attorney${staff && clientId ? `?client_id=${clientId}` : ""}`), [clientId]);
  const [fee, setFee] = useState("");
  const [start, setStart] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [poa, setPoa] = useState({ outorgante: "", outorgado: "", finalidade: "", orgao: "", valid_from: "", valid_until: "" });

  const wrap = async (fn: () => Promise<string>, reload: () => void) => {
    setMsg(null);
    try {
      setMsg({ kind: "ok", text: await fn() });
      reload();
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    }
  };
  const generate = (e: FormEvent) => {
    e.preventDefault();
    wrap(async () => {
      await post("/contracts", { client_id: clientId, monthly_fee: fee.replace(",", "."), start_date: start });
      return "Contrato gerado. O cliente deve aceitá-lo no próprio acesso.";
    }, contracts.reload);
  };
  const addPoa = (e: FormEvent) => {
    e.preventDefault();
    wrap(async () => {
      await post("/powers-of-attorney", { ...poa, client_id: clientId, orgao: poa.orgao || null, valid_until: poa.valid_until || null });
      return "Procuração registrada.";
    }, poas.reload);
  };

  return (
    <>
      <div className="topbar"><h1 tabIndex={-1} className="grow">Contratos, LGPD e procurações</h1></div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}

      {!!pending.data?.length && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Termos pendentes de aceite</h2>
          {pending.data.map((t) => (
            <details key={t.id}><summary>{t.title} (v{t.version})</summary><pre className="contract">{t.body}</pre></details>
          ))}
          <button style={{ marginTop: "1rem" }} onClick={() => wrap(async () => { await post("/terms/accept"); return "Termos aceitos."; }, pending.reload)}>
            Li e aceito todos os termos
          </button>
        </div>
      )}

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Contrato de prestação de serviços de BPO Financeiro (adesão)</h2>
        {staff && (
          <form className="row" onSubmit={generate}>
            <label>Honorários mensais (R$)<input value={fee} onChange={(e) => setFee(e.target.value)} required /></label>
            <label>Início<input type="date" value={start} onChange={(e) => setStart(e.target.value)} required /></label>
            <button disabled={!clientId}>Gerar contrato</button>
          </form>
        )}
        <table style={{ marginTop: "1rem" }}>
          <thead><tr><th>Início</th><th className="num">Mensalidade</th><th>Status</th><th>Aceite</th><th /></tr></thead>
          <tbody>
            {contracts.data?.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td>{dateBR(c.start_date)}</td><td className="num">{money(c.monthly_fee)}</td><td><span className="badge">{c.status}</span></td>
                  <td>{c.accepted_at ? `${dateBR(c.accepted_at)} · IP ${c.accepted_ip}` : "—"}</td>
                  <td>
                    <button className="secondary" onClick={() => setOpen(open === c.id ? null : c.id)}>Ver</button>{" "}
                    {!staff && c.status === "pendente" && (
                      <button onClick={() => wrap(async () => { await post(`/contracts/${c.id}/accept`); return "Contrato aceito eletronicamente."; }, contracts.reload)}>Aceitar</button>
                    )}
                  </td>
                </tr>
                {open === c.id && (
                  <tr key={`${c.id}-c`}><td colSpan={5}><pre className="contract">{c.content}</pre><p className="muted">SHA-256: {c.content_sha256}</p></td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Procurações</h2>
        {staff && (
          <form className="row" onSubmit={addPoa}>
            <label>Outorgante<input value={poa.outorgante} onChange={(e) => setPoa({ ...poa, outorgante: e.target.value })} required /></label>
            <label>Outorgado<input value={poa.outorgado} onChange={(e) => setPoa({ ...poa, outorgado: e.target.value })} required /></label>
            <label>Finalidade<input value={poa.finalidade} onChange={(e) => setPoa({ ...poa, finalidade: e.target.value })} required /></label>
            <label>Órgão<input value={poa.orgao} onChange={(e) => setPoa({ ...poa, orgao: e.target.value })} placeholder="RFB/e-CAC, banco…" /></label>
            <label>De<input type="date" value={poa.valid_from} onChange={(e) => setPoa({ ...poa, valid_from: e.target.value })} required /></label>
            <label>Até<input type="date" value={poa.valid_until} onChange={(e) => setPoa({ ...poa, valid_until: e.target.value })} /></label>
            <button disabled={!clientId}>Registrar</button>
          </form>
        )}
        <table style={{ marginTop: "1rem" }}>
          <thead><tr><th>Outorgante</th><th>Outorgado</th><th>Finalidade</th><th>Órgão</th><th>Validade</th><th /></tr></thead>
          <tbody>
            {poas.data?.map((p) => (
              <tr key={p.id} style={p.revoked_at ? { opacity: .5 } : undefined}>
                <td>{p.outorgante}</td><td>{p.outorgado}</td><td>{p.finalidade}</td><td>{p.orgao ?? "—"}</td>
                <td>{dateBR(p.valid_from)} a {p.valid_until ? dateBR(p.valid_until) : "indeterminado"}</td>
                <td>{p.revoked_at ? "revogada" : staff && <button className="secondary" onClick={() => wrap(async () => { await post(`/powers-of-attorney/${p.id}/revoke`); return "Procuração revogada."; }, poas.reload)}>Revogar</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Termos vigentes</h2>
        {terms.data?.map((t) => (
          <details key={t.id}><summary>{t.title} (v{t.version})</summary><pre className="contract">{t.body}</pre></details>
        ))}
      </div>
    </>
  );
}
