import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError, ChartAccount, cnpjMask, dateBR, money, post, Title, toDecimal } from "../api";
import { useSession } from "../App";
import { Alert, FieldError, Money, onListKeys, StatusTag, useLoad } from "../components/ui";

type Detail = Title & { history: { at: string; user: string; text: string }[] };
type Preview = { action: string; count: number; total: string; total_pagar: string; total_receber: string; eligible_ids: string[]; ineligible: { id: string; motivo: string }[] };
type Action = "aprovar" | "agendar" | "liquidar" | "cancelar";

const STATUS_LABEL: Record<string, string> = { aberto: "Em aberto", aprovado: "Aprovado", agendado: "Agendado", parcial: "Pago parcialmente", liquidado: "Liquidado", cancelado: "Cancelado" };
const ACTIONS: { key: Action; label: string; past: string }[] = [
  { key: "aprovar", label: "Aprovar", past: "aprovados" },
  { key: "agendar", label: "Agendar", past: "agendados" },
  { key: "liquidar", label: "Liquidar", past: "liquidados" },
  { key: "cancelar", label: "Cancelar", past: "cancelados" },
];

export default function PayablesPage() {
  const { clientId } = useSession();
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const urgency = params.get("urgency") ?? "";
  const status = params.get("status") ?? (urgency === "concluido" ? "" : "pendentes");
  const editing = params.get("titulo");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [batch, setBatch] = useState<Action | null>(null);

  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next);
  };
  const query = new URLSearchParams({ ...(kind && { kind }), ...(urgency && { urgency }), ...(status && { status }), ...(q && { q }) });
  const list = useLoad<Title[]>(
    () => (clientId ? api(`/clients/${clientId}/titles?${query}`) : Promise.resolve([])),
    [clientId, kind, urgency, status, q],
  );
  useEffect(() => setSelected(new Set()), [clientId]);

  const rows = list.data ?? [];
  const selectedRows = rows.filter((t) => selected.has(t.id));
  const selectedTotal = selectedRows.reduce((s, t) => s + Number(t.open_amount), 0);
  const toggle = (id: string) => {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id); else s.add(id);
    setSelected(s);
  };
  const toggleAll = () => setSelected(selected.size === rows.length ? new Set() : new Set(rows.map((t) => t.id)));

  if (editing) {
    return (
      <TitleEditor id={editing === "novo" ? null : editing}
        defaultKind={(kind || "pagar") as "pagar" | "receber"}
        onClose={(text) => { setParam("titulo", null); if (text) setMsg({ kind: "ok", text }); list.reload(); }} />
    );
  }

  return (
    <>
      <div className="topbar">
        <h1 tabIndex={-1} className="grow">Contas a pagar e receber</h1>
        <button onClick={() => setParam("titulo", "novo")} disabled={!clientId}>+ Novo título</button>
      </div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div className="card filters" role="group" aria-label="Filtros">
        <div className="segmented" role="radiogroup" aria-label="Tipo">
          {[["", "Todos"], ["pagar", "A pagar"], ["receber", "A receber"]].map(([v, l]) => (
            <button key={v} role="radio" aria-checked={kind === v} className={kind === v ? "on" : ""} onClick={() => setParam("kind", v || null)}>{l}</button>
          ))}
        </div>
        <div className="segmented" role="radiogroup" aria-label="Criticidade">
          {[["", "Todas"], ["atrasado", "Atrasados"], ["hoje", "Para hoje"], ["proximo", "No prazo"], ["concluido", "Concluídos"]].map(([v, l]) => (
            <button key={v} role="radio" aria-checked={urgency === v} className={urgency === v ? "on" : ""}
              onClick={() => { const n = new URLSearchParams(params); if (v) n.set("urgency", v); else n.delete("urgency"); n.delete("status"); setParams(n); }}>{l}</button>
          ))}
        </div>
        <label className="inline">
          <input type="checkbox" checked={status === ""} onChange={(e) => setParam("status", e.target.checked ? "" : null)} /> incluir liquidados e cancelados
        </label>
        <input type="search" aria-label="Filtrar por favorecido ou documento" placeholder="Filtrar favorecido, nº…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className="card">
        <Alert>{list.error}</Alert>
        <p className="muted kbd-hint">Teclado: ↑/↓ navega · Espaço seleciona · Enter abre o título</p>
        <table onKeyDown={onListKeys}>
          <thead>
            <tr>
              <th><input type="checkbox" aria-label="Selecionar todos" checked={rows.length > 0 && selected.size === rows.length} onChange={toggleAll} /></th>
              <th>Criticidade</th><th>Vencimento</th><th>Tipo</th><th>Favorecido / pagador</th><th>Documento</th><th>Situação</th><th className="num">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !list.loading && <tr><td colSpan={8} className="muted">Nenhum título neste filtro.</td></tr>}
            {rows.map((t) => (
              <tr key={t.id} data-row tabIndex={0} aria-selected={selected.has(t.id)} className={selected.has(t.id) ? "selected" : undefined}
                onKeyDown={(e) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === " ") { e.preventDefault(); toggle(t.id); }
                  if (e.key === "Enter") setParam("titulo", t.id);
                }}
                onDoubleClick={() => setParam("titulo", t.id)}>
                <td><input type="checkbox" tabIndex={-1} aria-label={`Selecionar ${t.counterparty_name}`} checked={selected.has(t.id)} onChange={() => toggle(t.id)} /></td>
                <td><StatusTag kind={t.urgency} /></td>
                <td>{dateBR(t.due_date)}</td>
                <td>{t.kind === "pagar" ? "A pagar" : "A receber"}</td>
                <td><button className="link" tabIndex={-1} onClick={() => setParam("titulo", t.id)}>{t.counterparty_name}</button>
                  {t.counterparty_doc && <div className="muted">{cnpjMask(t.counterparty_doc)}</div>}</td>
                <td>{t.document_number ?? "—"}{t.document_id && <span className="muted" title="Possui anexo"> · 📎</span>}</td>
                <td>{STATUS_LABEL[t.status]}</td>
                <td className="num"><Money v={t.kind === "pagar" ? -Number(t.open_amount) : t.open_amount} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected.size > 0 && (
        <div className="batchbar" role="region" aria-label="Ações em lote">
          <span><strong>{selected.size}</strong> selecionado(s) · saldo <strong>{money(selectedTotal)}</strong></span>
          <span className="grow" />
          {ACTIONS.map((a) => <button key={a.key} className={a.key === "cancelar" ? "secondary" : undefined} onClick={() => setBatch(a.key)}>{a.label}…</button>)}
          <button className="secondary" onClick={() => setSelected(new Set())}>Limpar</button>
        </div>
      )}
      {batch && (
        <BatchDialog action={batch} ids={[...selected]}
          onClose={(done) => {
            setBatch(null);
            if (done) { setMsg({ kind: "ok", text: done }); setSelected(new Set()); list.reload(); }
          }} />
      )}
    </>
  );
}

function BatchDialog({ action, ids, onClose }: { action: Action; ids: string[]; onClose: (done?: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [when, setWhen] = useState(new Date().toISOString().slice(0, 10));
  const meta = ACTIONS.find((a) => a.key === action)!;

  useEffect(() => {
    if (!ref.current?.open) ref.current?.showModal();
    post<Preview>("/titles/batch/preview", { title_ids: ids, action }).then(setPreview).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (preview?.count) confirmRef.current?.focus(); // foco no Confirmar só depois de exibir o total
  }, [preview]);
  const confirm = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await post<Preview>("/titles/batch", { title_ids: preview!.eligible_ids, action, expected_total: preview!.total, on_date: when });
      onClose(`${r.count} título(s) ${meta.past} · total ${money(r.total)}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <dialog ref={ref} className="dialog" aria-labelledby="batch-title" onClose={() => onClose()}>
      <form onSubmit={confirm} className="form">
        <h2 id="batch-title" style={{ margin: 0 }}>{meta.label} títulos em lote</h2>
        <Alert>{error}</Alert>
        {!preview && !error && <p className="muted">Calculando…</p>}
        {preview && (
          <>
            <div className="summary">
              <div><span className="muted">Títulos</span><strong>{preview.count}</strong></div>
              {Number(preview.total_pagar) > 0 && <div><span className="muted">A pagar</span><strong className="neg">{money(preview.total_pagar)}</strong></div>}
              {Number(preview.total_receber) > 0 && <div><span className="muted">A receber</span><strong className="pos">{money(preview.total_receber)}</strong></div>}
              <div><span className="muted">Total do lote</span><strong>{money(preview.total)}</strong></div>
            </div>
            {preview.ineligible.length > 0 && (
              <Alert kind="warn">
                {preview.ineligible.length} título(s) ficarão de fora:
                <ul>{preview.ineligible.map((i) => <li key={i.id}>{i.motivo}</li>)}</ul>
              </Alert>
            )}
            {(action === "agendar" || action === "liquidar") && (
              <label>{action === "agendar" ? "Agendar para" : "Data do pagamento/recebimento"}
                <input type="date" value={when} onChange={(e) => setWhen(e.target.value)} required />
              </label>
            )}
          </>
        )}
        <div className="row">
          <button type="submit" ref={confirmRef} disabled={!preview || preview.count === 0}>Confirmar {meta.label.toLowerCase()} {preview ? money(preview.total) : ""}</button>
          <button type="button" className="secondary" onClick={() => ref.current?.close()}>Voltar (Esc)</button>
        </div>
      </form>
    </dialog>
  );
}

const EMPTY = { kind: "pagar", counterparty_name: "", counterparty_doc: "", document_number: "", description: "", issue_date: new Date().toISOString().slice(0, 10), due_date: "", amount: "", account_id: "" };

function TitleEditor({ id, defaultKind, onClose }: { id: string | null; defaultKind: "pagar" | "receber"; onClose: (msg?: string) => void }) {
  const { clientId } = useSession();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [f, setF] = useState({ ...EMPTY, kind: defaultKind });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const accounts = useLoad<ChartAccount[]>(() => api("/chart-accounts"), []);
  const first = useRef<HTMLInputElement>(null);
  const readOnly = !!detail && ["liquidado", "cancelado"].includes(detail.status);

  const load = async (tid: string) => {
    const d = await api<Detail>(`/titles/${tid}`);
    setDetail(d);
    setF({ kind: d.kind, counterparty_name: d.counterparty_name, counterparty_doc: d.counterparty_doc ?? "", document_number: d.document_number ?? "", description: d.description ?? "", issue_date: d.issue_date, due_date: d.due_date, amount: d.amount, account_id: d.account_id ?? "" });
  };
  useEffect(() => {
    if (id) load(id).catch((e) => setError(e.message));
    first.current?.focus();
  }, [id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector("dialog[open]")) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    setError(null);
    const payload = { ...f, amount: toDecimal(f.amount), account_id: f.account_id || null, counterparty_doc: f.counterparty_doc || null, document_number: f.document_number || null, description: f.description || null };
    try {
      let saved: Title;
      if (id) {
        const { kind: _k, counterparty_doc: _d, ...upd } = payload;
        saved = await api<Title>(`/titles/${id}`, { method: "PATCH", body: JSON.stringify(upd) });
      } else {
        saved = await post<Title>("/titles", { ...payload, client_id: clientId });
      }
      if (pendingFile) {
        const fd = new FormData();
        fd.append("file", pendingFile);
        await post(`/titles/${saved.id}/attachment`, fd);
      }
      onClose(`Título ${saved.document_number ?? saved.counterparty_name} salvo.`);
    } catch (err) {
      const ae = err as ApiError;
      setErrors(ae.fields ?? {});
      setError(ae.message);
      const firstField = Object.keys(ae.fields ?? {})[0];
      if (firstField) document.getElementById(`f-${firstField}`)?.focus();
    } finally {
      setBusy(false);
    }
  };
  const attachNow = async (file: File | undefined) => {
    if (!file) return;
    if (!id) return setPendingFile(file);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await post(`/titles/${id}/attachment`, fd);
      await load(id);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const field = (k: keyof typeof EMPTY, label: string, input: React.ReactNode) => (
    <label htmlFor={`f-${k}`}>{label}{input}<FieldError id={`e-${k}`} msg={errors[k]} /></label>
  );
  const inv = (k: string) => ({ id: `f-${k}`, "aria-invalid": !!errors[k] || undefined, "aria-describedby": errors[k] ? `e-${k}` : undefined, disabled: readOnly });

  return (
    <>
      <div className="topbar">
        <h1 tabIndex={-1} className="grow">{id ? `Título ${detail?.document_number ?? ""}` : "Novo título"}</h1>
        {detail && <><StatusTag kind={detail.urgency} /><span className="badge">{STATUS_LABEL[detail.status]}</span></>}
        <button className="secondary" onClick={() => onClose()}>Voltar à lista (Esc)</button>
      </div>
      <div className="split">
        <section className="card viewer" aria-label="Documento para conferência">
          <DocViewer documentId={detail?.document_id ?? null} pendingFile={pendingFile} />
          {!readOnly && (
            <label className="attach">{detail?.document_id || pendingFile ? "Substituir anexo" : "Anexar boleto ou nota (PDF, imagem ou XML)"}
              <input type="file" accept=".pdf,.png,.jpg,.jpeg,.xml" onChange={(e) => attachNow(e.target.files?.[0])} />
            </label>
          )}
        </section>
        <section className="card" aria-label="Dados do título">
          <Alert>{error}</Alert>
          {readOnly && <Alert kind="warn">Título {STATUS_LABEL[detail!.status].toLowerCase()}: somente consulta.</Alert>}
          <form className="form grid2" onSubmit={save} noValidate>
            {field("kind", "Tipo", <select {...inv("kind")} value={f.kind} onChange={set("kind")} disabled={!!id || readOnly}><option value="pagar">A pagar</option><option value="receber">A receber</option></select>)}
            {field("counterparty_name", f.kind === "pagar" ? "Favorecido" : "Pagador", <input ref={first} {...inv("counterparty_name")} value={f.counterparty_name} onChange={set("counterparty_name")} required />)}
            {field("counterparty_doc", "CPF/CNPJ", <input {...inv("counterparty_doc")} value={f.counterparty_doc} onChange={set("counterparty_doc")} disabled={!!id || readOnly} inputMode="numeric" />)}
            {field("document_number", "Nº do documento", <input {...inv("document_number")} value={f.document_number} onChange={set("document_number")} />)}
            {field("issue_date", "Data de emissão", <input type="date" {...inv("issue_date")} value={f.issue_date} onChange={set("issue_date")} required />)}
            {field("due_date", "Data de vencimento", <input type="date" {...inv("due_date")} value={f.due_date} onChange={set("due_date")} required />)}
            {field("amount", "Valor (R$)", <input {...inv("amount")} value={f.amount} onChange={set("amount")} inputMode="decimal" placeholder="0,00" required />)}
            {field("account_id", "Conta gerencial", (
              <select {...inv("account_id")} value={f.account_id} onChange={set("account_id")}>
                <option value="">Selecione…</option>
                {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}
              </select>
            ))}
            <div className="span2">{field("description", "Descrição", <input {...inv("description")} value={f.description} onChange={set("description")} />)}</div>
            {detail && Number(detail.paid_amount) > 0 && <p className="span2 muted">Pago: {money(detail.paid_amount)} · saldo {money(detail.open_amount)}</p>}
            {!readOnly && (
              <div className="row span2">
                <button type="submit" disabled={busy}>{busy ? "Salvando…" : "Salvar (Enter)"}</button>
                <button type="button" className="secondary" onClick={() => onClose()}>Cancelar</button>
              </div>
            )}
          </form>
          {detail && (
            <>
              <h2>Histórico</h2>
              <ol className="feed">
                {detail.history.length === 0 && <li className="muted">Sem registros.</li>}
                {detail.history.map((h, i) => (
                  <li key={i}><time dateTime={h.at}>{new Date(h.at + "Z").toLocaleString("pt-BR")}</time> {h.text}</li>
                ))}
              </ol>
            </>
          )}
        </section>
      </div>
    </>
  );
}

function DocViewer({ documentId, pendingFile }: { documentId: string | null; pendingFile: File | null }) {
  const [view, setView] = useState<{ url?: string; type: string; text?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const source = useMemo(() => pendingFile ?? documentId, [pendingFile, documentId]);
  useEffect(() => {
    let url: string | undefined;
    setView(null);
    setError(null);
    (async () => {
      if (!source) return;
      const blob = source instanceof File ? source : await api<Blob>(`/documents/${source}/download`);
      const type = blob.type || "application/octet-stream";
      if (type.includes("xml") || type.startsWith("text/")) setView({ type, text: await blob.text() });
      else {
        url = URL.createObjectURL(blob);
        setView({ url, type });
      }
    })().catch((e) => setError(e.message));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [source]);

  if (error) return <Alert>{error}</Alert>;
  if (!source) return <div className="viewer-empty"><p>Nenhum documento anexado.</p><p className="muted">Anexe o boleto ou a nota para conferir lado a lado com os campos.</p></div>;
  if (!view) return <p className="muted">Carregando documento…</p>;
  if (view.text !== undefined) return <pre className="viewer-text">{view.text}</pre>;
  if (view.type.startsWith("image/")) return <img className="viewer-frame" src={view.url} alt="Documento anexado" />;
  return <iframe className="viewer-frame" src={view.url} title="Documento anexado" />;
}
