import { FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ChartAccount, dateBR, pct, post } from "../api";
import { useSession } from "../App";
import { Alert, Money, onListKeys, StatusTag, useLoad } from "../components/ui";

type BankAccount = { id: string; kind: string; bank_name: string; agencia: string | null; conta: string | null; source: string; connection_status: string; last_sync_at: string | null; last_sync_error: string | null };
type Tx = {
  id: string; date: string; description: string; amount: string; account_id: string | null;
  classified_by: string | null; confidence: number | null; suggested_account_id: string | null;
};

export default function BankingPage() {
  const { clientId } = useSession();
  const [params] = useSearchParams();
  const [status, setStatus] = useState(params.get("status") ?? "pendente");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const accounts = useLoad<BankAccount[]>(
    () => (clientId ? api(`/clients/${clientId}/bank-accounts`) : Promise.resolve([])), [clientId]);
  const chart = useLoad<ChartAccount[]>(() => api("/chart-accounts"), []);
  const txs = useLoad<Tx[]>(
    () => (clientId ? api(`/clients/${clientId}/transactions${status ? `?status=${status}` : ""}`) : Promise.resolve([])),
    [clientId, status],
  );
  const name = (id: string | null) => {
    const a = chart.data?.find((c) => c.id === id);
    return a ? `${a.code} ${a.name}` : "—";
  };
  const wrap = async (fn: () => Promise<string>) => {
    setMsg(null);
    try {
      setMsg({ kind: "ok", text: await fn() });
      setSelected(new Set());
      txs.reload();
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    }
  };

  const upload = (accountId: string, file: File | undefined) => file && wrap(async () => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await post<{ importados: number; duplicados: number; classificacao: Record<string, number> }>(`/bank-accounts/${accountId}/statements`, fd);
    return `${r.importados} lançamentos importados (${r.duplicados} duplicados ignorados). IA: ${r.classificacao.aplicados} classificados automaticamente, ${r.classificacao.sugeridos} sugestões para revisar.`;
  });
  const classify = () => wrap(async () => {
    await post("/transactions/classify", { transaction_ids: [...selected], account_id: target });
    return "Classificação salva. A IA usará esse histórico nos próximos extratos.";
  });
  const accept = () => wrap(async () => {
    await post("/transactions/accept-suggestions", { transaction_ids: [...selected] });
    return "Sugestões confirmadas.";
  });
  const auto = () => wrap(async () => {
    const r = await post<Record<string, number>>(`/clients/${clientId}/transactions/auto-classify`);
    return `IA: ${r.aplicados} classificados, ${r.sugeridos} sugestões, ${r.sem_sugestao} sem sugestão.`;
  });
  const toggle = (id: string) => {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id); else s.add(id);
    setSelected(s);
  };

  return (
    <>
      <div className="topbar">
        <h1 tabIndex={-1} className="grow">Extratos bancários</h1>
      </div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Contas correntes</h2>
        <table>
          <thead><tr><th>Banco</th><th>Agência/Conta</th><th>Integração</th><th>Última atualização</th><th>Importar OFX/CSV</th></tr></thead>
          <tbody>
            {accounts.data?.filter((a) => a.kind === "corrente").map((a) => (
              <tr key={a.id}>
                <td>{a.bank_name}</td><td>{a.agencia ?? "—"} / {a.conta ?? "—"}</td><td><StatusTag kind={a.connection_status} />{a.last_sync_error && <div className="field-error">{a.last_sync_error}</div>}</td>
                <td>{a.last_sync_at ? new Date(a.last_sync_at + "Z").toLocaleString("pt-BR") : "—"}</td>
                <td><input type="file" accept=".ofx,.csv,.txt" onChange={(e) => upload(a.id, e.target.files?.[0])} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <NewAccount clientId={clientId} kind="corrente" onDone={accounts.reload} />
      </div>
      <div className="card">
        <div className="row" style={{ marginBottom: "1rem" }}>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filtro">
            <option value="pendente">A classificar</option>
            <option value="sugerido">Com sugestão da IA</option>
            <option value="classificado">Classificados</option>
            <option value="">Todos</option>
          </select>
          <button className="secondary" onClick={auto}>Replicar classificação (IA)</button>
          <span className="grow" />
          <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Conta">
            <option value="">Classificar selecionados em…</option>
            {chart.data?.map((a) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}
          </select>
          <button disabled={!selected.size || !target} onClick={classify}>Classificar ({selected.size})</button>
          <button className="secondary" disabled={!selected.size} onClick={accept}>Aceitar sugestões</button>
        </div>
        <table onKeyDown={onListKeys}>
          <thead><tr><th /><th>Data</th><th>Histórico</th><th className="num">Valor</th><th>Conta</th><th>Sugestão IA</th><th>Origem</th></tr></thead>
          <tbody>
            {txs.data?.length === 0 && <tr><td colSpan={7} className="muted">Nenhum lançamento neste filtro.</td></tr>}
            {txs.data?.map((t) => (
              <tr key={t.id}>
                <td><input data-row type="checkbox" checked={selected.has(t.id)} onChange={() => toggle(t.id)} aria-label={`Selecionar ${t.description}`} /></td>
                <td>{dateBR(t.date)}</td>
                <td>{t.description}</td>
                <td className="num"><Money v={t.amount} /></td>
                <td>{name(t.account_id)}</td>
                <td>{t.suggested_account_id && !t.account_id ? <>{name(t.suggested_account_id)} <span className="muted">{pct((t.confidence ?? 0) * 100)}</span></> : "—"}</td>
                <td>{t.classified_by ? <span className="badge">{t.classified_by}</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function NewAccount({ clientId, kind, onDone }: { clientId: string; kind: "corrente" | "aplicacao"; onDone: () => void }) {
  const [f, setF] = useState({ bank_name: "", bank_code: "", agencia: "", conta: "", product_name: "" });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post("/bank-accounts", { ...f, client_id: clientId, kind, bank_code: f.bank_code || null });
      setF({ bank_name: "", bank_code: "", agencia: "", conta: "", product_name: "" });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <form className="row" onSubmit={submit} style={{ marginTop: "1rem" }}>
      <Alert>{error}</Alert>
      <label>Banco<input value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} required /></label>
      <label>Cód.<input size={4} value={f.bank_code} onChange={(e) => setF({ ...f, bank_code: e.target.value })} /></label>
      <label>Agência<input size={6} value={f.agencia} onChange={(e) => setF({ ...f, agencia: e.target.value })} /></label>
      <label>Conta<input size={10} value={f.conta} onChange={(e) => setF({ ...f, conta: e.target.value })} /></label>
      {kind === "aplicacao" && <label>Produto<input value={f.product_name} onChange={(e) => setF({ ...f, product_name: e.target.value })} placeholder="CDB, Fundo DI…" /></label>}
      <button disabled={!clientId}>Adicionar conta</button>
    </form>
  );
}
