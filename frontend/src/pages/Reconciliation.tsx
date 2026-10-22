import { useEffect, useRef, useState } from "react";
import { api, dateBR, money, post, Title, Transaction } from "../api";
import { useSession } from "../App";
import { Alert, Money, onListKeys, StatusTag, useLoad } from "../components/ui";

type Suggestion = { transaction: Transaction; title: Title; score: number; difference: string; actions: string[] };
type Connection = { id: string; kind: string; bank_name: string; conta: string | null; connection_status: string; last_sync_at: string | null; last_sync_error: string | null };
type Action = "exato" | "juros" | "desconto" | "parcial";

const ACTION_INFO: Record<Action, { label: string; key: string; help: (d: number, t: Title) => string }> = {
  exato: { label: "Confirmar", key: "Enter", help: () => "Valores idênticos" },
  juros: { label: "Criar juros/multa", key: "J", help: (d, t) => `Registra ${money(d)} de juros/multa ${t.kind === "pagar" ? "pagos" : "recebidos"} e liquida o título` },
  desconto: { label: "Desconto", key: "D", help: (d, t) => `Registra ${money(Math.abs(d))} de desconto ${t.kind === "pagar" ? "obtido" : "concedido"} e liquida o título` },
  parcial: { label: "Lançamento parcial", key: "P", help: (d) => `Baixa parcial; o título fica com saldo de ${money(Math.abs(d))}` },
};

export default function ReconciliationPage() {
  const { clientId } = useSession();
  const sug = useLoad<Suggestion[]>(() => (clientId ? api(`/clients/${clientId}/reconciliation/suggestions`) : Promise.resolve([])), [clientId]);
  const conns = useLoad<Connection[]>(() => (clientId ? api(`/clients/${clientId}/bank-accounts`) : Promise.resolve([])), [clientId]);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string; undo?: string } | null>(null);
  const [errorFor, setErrorFor] = useState<Record<string, string>>({});
  const listRef = useRef<HTMLUListElement>(null);

  const apply = async (s: Suggestion, action: Action, titleId = s.title.id) => {
    try {
      await post("/reconciliations", { transaction_id: s.transaction.id, title_id: titleId, action });
      setMsg({ kind: "ok", text: `Conciliado: ${s.transaction.description} × ${s.title.counterparty_name} (${ACTION_INFO[action].label.toLowerCase()}).`, undo: s.transaction.id });
      setErrorFor({});
      await sug.reload();
      listRef.current?.querySelector<HTMLElement>("[data-row]")?.focus();
    } catch (e) {
      setErrorFor({ [s.transaction.id]: (e as Error).message });
    }
  };
  const undo = async (txId: string) => {
    try {
      await api(`/reconciliations/${txId}`, { method: "DELETE" });
      setMsg({ kind: "ok", text: "Conciliação desfeita." });
      sug.reload();
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    }
  };

  const onCardKey = (s: Suggestion) => (e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    const map: Record<string, Action> = { Enter: "exato", j: "juros", J: "juros", d: "desconto", D: "desconto", p: "parcial", P: "parcial" };
    const action = map[e.key];
    if (!action) return;
    const allowed = s.actions.includes(action) ? action : e.key === "Enter" ? (s.actions[0] as Action) : null;
    if (allowed) { e.preventDefault(); apply(s, allowed); }
  };
  const problems = (conns.data ?? []).filter((c) => c.kind === "corrente" && ["reautenticar", "erro"].includes(c.connection_status));

  return (
    <>
      <div className="topbar"><h1 tabIndex={-1} className="grow">Conciliação bancária</h1></div>

      <section className="card connections" aria-label="Status das integrações bancárias">
        {(conns.data ?? []).filter((c) => c.kind === "corrente").map((c) => (
          <span key={c.id} className="conn"><StatusTag kind={c.connection_status} /> {c.bank_name} {c.conta}
            <span className="muted"> · {c.last_sync_at ? `atualizado ${new Date(c.last_sync_at + "Z").toLocaleString("pt-BR")}` : "sem sincronização"}</span>
          </span>
        ))}
        {problems.map((c) => <Alert key={c.id} kind="warn">{c.bank_name}: {c.last_sync_error ?? "a conexão precisa de atenção"}. Os lançamentos desse banco podem estar desatualizados.</Alert>)}
      </section>

      {msg && (
        <Alert kind={msg.kind}>{msg.text} {msg.undo && <button className="link" onClick={() => undo(msg.undo!)}>Desfazer</button>}</Alert>
      )}
      <Alert>{sug.error}</Alert>
      <p className="muted kbd-hint">Teclado: ↑/↓ entre sugestões · Enter confirma · J juros/multa · D desconto · P parcial</p>
      {sug.data?.length === 0 && <div className="card"><StatusTag kind="concluido" label="Nada a conciliar" /> Não há sugestões pendentes para esta empresa.</div>}

      <ul className="matches" ref={listRef} onKeyDown={onListKeys}>
        {sug.data?.map((s) => {
          const diff = Number(s.difference);
          return (
            <li key={s.transaction.id} data-row tabIndex={0} className="match" onKeyDown={onCardKey(s)}
              aria-label={`Extrato ${s.transaction.description} ${money(s.transaction.amount)}; sugerido ${s.title.counterparty_name} ${money(s.title.open_amount)}`}>
              <div className="side">
                <span className="muted">Extrato bancário · {dateBR(s.transaction.date)}</span>
                <strong>{s.transaction.description}</strong>
                <span className="amount"><Money v={s.transaction.amount} /></span>
              </div>
              <div className="link-col" aria-hidden="true">
                <span className="score">{Math.round(s.score * 100)}%</span>
                <span>⇄</span>
              </div>
              <div className="side">
                <span className="muted">Título a {s.title.kind} · vence {dateBR(s.title.due_date)} <StatusTag kind={s.title.urgency} /></span>
                <strong>{s.title.counterparty_name}</strong>
                <span className="muted">{s.title.document_number ?? "sem nº"}</span>
                <span className="amount"><Money v={s.title.kind === "pagar" ? -Number(s.title.open_amount) : s.title.open_amount} /></span>
              </div>
              <div className="decide">
                {diff === 0 ? (
                  <StatusTag kind="concluido" label="Valores conferem" />
                ) : (
                  <StatusTag kind="atencao" label={`Diferença de ${money(Math.abs(diff))} (${diff > 0 ? "extrato maior" : "extrato menor"})`} />
                )}
                <div className="row">
                  {(s.actions as Action[]).map((a, i) => (
                    <button key={a} className={i === 0 ? undefined : "secondary"} onClick={() => apply(s, a)} title={ACTION_INFO[a].help(diff, s.title)}>
                      {ACTION_INFO[a].label} <kbd>{ACTION_INFO[a].key}</kbd>
                    </button>
                  ))}
                </div>
                <span className="muted">{ACTION_INFO[s.actions[0] as Action].help(diff, s.title)}</span>
                {errorFor[s.transaction.id] && <span className="field-error" role="alert">{errorFor[s.transaction.id]}</span>}
              </div>
            </li>
          );
        })}
      </ul>
      <ManualMatch onDone={(t) => { setMsg({ kind: "ok", text: t }); sug.reload(); }} />
    </>
  );
}

/** Lançamentos sem sugestão automática: o operador escolhe o título manualmente. */
function ManualMatch({ onDone }: { onDone: (msg: string) => void }) {
  const { clientId } = useSession();
  const pending = useLoad<Transaction[]>(() => (clientId ? api(`/clients/${clientId}/reconciliation/pending`) : Promise.resolve([])), [clientId]);
  const titles = useLoad<Title[]>(() => (clientId ? api(`/clients/${clientId}/titles?status=pendentes`) : Promise.resolve([])), [clientId]);
  const [txId, setTxId] = useState("");
  const [titleId, setTitleId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const tx = pending.data?.find((t) => t.id === txId);
  const candidates = (titles.data ?? []).filter((t) => tx && (Number(tx.amount) > 0 ? t.kind === "receber" : t.kind === "pagar"));
  const title = candidates.find((t) => t.id === titleId);
  const diff = tx && title ? Math.abs(Number(tx.amount)) - Number(title.open_amount) : 0;
  const actions: Action[] = !title ? [] : diff === 0 ? ["exato"] : diff > 0 ? ["juros"] : ["desconto", "parcial"];
  useEffect(() => setTitleId(""), [txId]);

  const go = async (action: Action) => {
    setError(null);
    try {
      await post("/reconciliations", { transaction_id: txId, title_id: titleId, action });
      onDone(`Conciliado manualmente: ${tx!.description} × ${title!.counterparty_name}.`);
      setTxId("");
      pending.reload();
      titles.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="card" aria-labelledby="manual">
      <h2 id="manual" style={{ marginTop: 0 }}>Conciliação manual</h2>
      <div className="row">
        <label>Lançamento do extrato
          <select value={txId} onChange={(e) => setTxId(e.target.value)}>
            <option value="">Selecione…</option>
            {pending.data?.map((t) => <option key={t.id} value={t.id}>{dateBR(t.date)} · {t.description} · {money(t.amount)}</option>)}
          </select>
        </label>
        <label>Título em aberto
          <select value={titleId} onChange={(e) => setTitleId(e.target.value)} disabled={!tx}>
            <option value="">{tx ? `Títulos a ${Number(tx.amount) > 0 ? "receber" : "pagar"}…` : "Escolha o lançamento primeiro"}</option>
            {candidates.map((t) => <option key={t.id} value={t.id}>{dateBR(t.due_date)} · {t.counterparty_name} · {t.document_number ?? ""} · saldo {money(t.open_amount)}</option>)}
          </select>
        </label>
        {actions.map((a, i) => <button key={a} className={i ? "secondary" : undefined} onClick={() => go(a)}>{ACTION_INFO[a].label}</button>)}
      </div>
      {title && diff !== 0 && <p className="muted">{ACTION_INFO[actions[0]].help(diff, title)}</p>}
      <Alert>{error}</Alert>
    </section>
  );
}
