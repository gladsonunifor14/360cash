import { FormEvent, useMemo, useState } from "react";
import { api, ApiError, post } from "../api";
import { useSession } from "../App";
import { Alert, FieldError, StatusTag, useLoad } from "../components/ui";
import { ConfirmDialog } from "./Users";

type Version = { id: string; kind: string; version: number; title: string; body: string; content_sha256: string; is_active: boolean; created_at: string; is_current: boolean; acceptances: number };
type Evidence = { id: string; term_id: string; user_id: string; user_name: string; user_email: string; term_kind: string; term_title: string; term_version: number; accepted_at: string; ip: string | null; user_agent: string | null; content_sha256: string };
type U = { id: string; name: string; email: string; is_active: boolean };

const KINDS: Record<string, { label: string; help: string }> = {
  privacidade: { label: "Política de Privacidade (LGPD)", help: "Finalidades, bases legais, compartilhamentos, retenção e direitos do titular" },
  confidencialidade: { label: "Termo de Confidencialidade", help: "Sigilo profissional e das informações financeiras" },
  uso: { label: "Termos de Uso", help: "Regras de acesso e uso da plataforma" },
};
const fmt = (s: string) => new Date(s + "Z").toLocaleString("pt-BR");

export default function TermsPage() {
  const { user } = useSession();
  const isAdmin = user.role === "admin";
  const history = useLoad<Version[]>(() => api("/terms/history"), []);
  const evidence = useLoad<Evidence[]>(() => api("/terms/acceptances"), []);
  const users = useLoad<U[]>(() => (isAdmin ? api("/users") : Promise.resolve([])), []);
  const [tab, setTab] = useState<"vigentes" | "evidencias">("vigentes");
  const [publishing, setPublishing] = useState<string | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const current = (history.data ?? []).filter((v) => v.is_current);
  const activeUsers = (users.data ?? []).filter((u) => u.is_active);
  const acceptedBy = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of evidence.data ?? []) {
      if (!m.has(e.term_id)) m.set(e.term_id, new Set());
      m.get(e.term_id)!.add(e.user_id);
    }
    return m;
  }, [evidence.data]);
  const evRows = (evidence.data ?? []).filter((e) => !kindFilter || e.term_kind === kindFilter);

  const exportCsv = () => {
    const head = ["usuario", "email", "termo", "versao", "aceito_em", "ip", "navegador", "sha256"];
    const lines = evRows.map((e) => [e.user_name, e.user_email, e.term_title, e.term_version, e.accepted_at, e.ip ?? "", e.user_agent ?? "", e.content_sha256]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`).join(";"));
    const blob = new Blob(["﻿" + [head.join(";"), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `evidencias-aceite-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <div className="topbar">
        <h1 tabIndex={-1} className="grow">Termos e LGPD</h1>
        <div className="segmented" role="tablist" aria-label="Seções">
          <button role="tab" aria-selected={tab === "vigentes"} className={tab === "vigentes" ? "on" : ""} onClick={() => setTab("vigentes")}>Termos vigentes</button>
          <button role="tab" aria-selected={tab === "evidencias"} className={tab === "evidencias" ? "on" : ""} onClick={() => setTab("evidencias")}>Evidências de aceite</button>
        </div>
      </div>
      {msg && <Alert kind="ok">{msg}</Alert>}
      <Alert>{history.error || evidence.error}</Alert>

      {tab === "vigentes" && (
        <>
          <div className="term-grid">
            {Object.entries(KINDS).map(([kind, info]) => {
              const v = current.find((c) => c.kind === kind);
              const accepted = v ? acceptedBy.get(v.id) ?? new Set() : new Set<string>();
              const missing = activeUsers.filter((u) => !accepted.has(u.id));
              const versions = (history.data ?? []).filter((h) => h.kind === kind);
              return (
                <section key={kind} className="card" aria-labelledby={`t-${kind}`}>
                  <h2 id={`t-${kind}`} style={{ marginTop: 0 }}>{info.label}</h2>
                  <p className="muted">{info.help}</p>
                  {v ? (
                    <>
                      <p><span className="badge">Versão {v.version}</span> publicada em {fmt(v.created_at)}</p>
                      <p className="muted mono">SHA-256 {v.content_sha256.slice(0, 16)}…</p>
                      {isAdmin && (
                        missing.length === 0
                          ? <StatusTag kind="concluido" label={activeUsers.length === 1 ? "Aceito pelo único usuário ativo" : `Aceito por todos os ${activeUsers.length} usuários ativos`} />
                          : <>
                              <StatusTag kind="hoje" label={`Aceite pendente: ${missing.length} de ${activeUsers.length} usuário(s) ativo(s)`} />
                              <details><summary className="muted">Ver quem falta</summary>
                                <ul className="plain">{missing.map((u) => <li key={u.id}>{u.name} <span className="muted">{u.email}</span></li>)}</ul>
                              </details>
                            </>
                      )}
                    </>
                  ) : <StatusTag kind="atencao" label="Nenhuma versão publicada" />}
                  <div className="row" style={{ marginTop: "1rem" }}>
                    {v && <button className="secondary" onClick={() => setViewing(viewing === v.id ? null : v.id)}>{viewing === v.id ? "Ocultar texto" : "Ler texto"}</button>}
                    {isAdmin && <button onClick={() => setPublishing(kind)}>Publicar nova versão</button>}
                  </div>
                  {v && viewing === v.id && <pre className="contract">{v.body}</pre>}
                  {versions.length > 1 && (
                    <details style={{ marginTop: ".75rem" }}>
                      <summary className="muted">Versões anteriores ({versions.length - 1})</summary>
                      <ul className="plain">
                        {versions.filter((h) => !h.is_current).map((h) => (
                          <li key={h.id}><span className="badge">v{h.version}</span> {h.title} <span className="muted">· {fmt(h.created_at)} · {h.acceptances} aceite(s)</span></li>
                        ))}
                      </ul>
                    </details>
                  )}
                </section>
              );
            })}
          </div>
          {!isAdmin && <p className="muted">Somente administradores publicam novas versões.</p>}
        </>
      )}

      {tab === "evidencias" && (
        <div className="card">
          <div className="row" style={{ marginBottom: ".75rem" }}>
            <select aria-label="Termo" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
              <option value="">Todos os termos</option>
              {Object.entries(KINDS).map(([k, i]) => <option key={k} value={k}>{i.label}</option>)}
            </select>
            <span className="grow" />
            <button className="secondary" onClick={exportCsv} disabled={!evRows.length}>Exportar CSV</button>
          </div>
          <p className="muted">Cada aceite guarda usuário, versão, data/hora, IP, navegador e o hash do texto exatamente como foi aceito. Use como prova em auditorias e pedidos de titulares (LGPD art. 8º, §2º).</p>
          <table>
            <thead><tr><th>Usuário</th><th>Termo</th><th>Aceito em</th><th>IP</th><th>Hash do texto</th></tr></thead>
            <tbody>
              {evRows.length === 0 && <tr><td colSpan={5} className="muted">Nenhum aceite registrado.</td></tr>}
              {evRows.map((e) => (
                <tr key={e.id}>
                  <td>{e.user_name}<div className="muted">{e.user_email}</div></td>
                  <td>{e.term_title} <span className="badge">v{e.term_version}</span></td>
                  <td>{fmt(e.accepted_at)}</td>
                  <td>{e.ip ?? "—"}</td>
                  <td className="muted mono" title={e.content_sha256}>{e.content_sha256.slice(0, 16)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {publishing && (
        <PublishDialog kind={publishing} base={current.find((c) => c.kind === publishing)}
          onClose={(text) => { setPublishing(null); if (text) { setMsg(text); history.reload(); evidence.reload(); } }} />
      )}
    </>
  );
}

function PublishDialog({ kind, base, onClose }: { kind: string; base?: Version; onClose: (msg?: string) => void }) {
  const [f, setF] = useState({ title: base?.title ?? KINDS[kind].label, body: base?.body ?? "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const changed = !base || f.body.trim() !== base.body.trim() || f.title !== base.title;

  const publish = async () => {
    try {
      const t = await post<{ version: number }>("/terms", { kind, ...f });
      onClose(`${KINDS[kind].label} v${t.version} publicada. Todos os usuários verão o novo texto e precisarão aceitá-lo no próximo acesso.`);
    } catch (err) {
      const ae = err as ApiError;
      setErrors(ae.fields ?? {});
      setError(ae.message);
      setConfirm(false);
    }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); setConfirm(true); };

  return (
    <div className="card publish" role="region" aria-labelledby="pub-title">
      <h2 id="pub-title" style={{ marginTop: 0 }}>Nova versão: {KINDS[kind].label}</h2>
      <Alert kind="warn">Versões publicadas não podem ser alteradas. Ao publicar, todos os usuários precisarão aceitar o novo texto. Revise com o jurídico do escritório.</Alert>
      <Alert>{error}</Alert>
      <form className="form" onSubmit={submit} noValidate>
        <label htmlFor="f-title">Título<input id="f-title" aria-invalid={!!errors.title || undefined} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /><FieldError id="e-title" msg={errors.title} /></label>
        <label htmlFor="f-body">Texto (Markdown)
          <textarea id="f-body" rows={18} aria-invalid={!!errors.body || undefined} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} />
          <span className="muted">{f.body.length} caracteres (mínimo 50)</span>
          <FieldError id="e-body" msg={errors.body} />
        </label>
        <div className="row">
          <button type="submit" disabled={!changed}>Revisar e publicar</button>
          <button type="button" className="secondary" onClick={() => onClose()}>Cancelar</button>
          {!changed && <span className="muted">Altere o texto ou o título para publicar uma nova versão.</span>}
        </div>
      </form>
      {confirm && (
        <ConfirmDialog title={`Publicar ${KINDS[kind].label} v${(base?.version ?? 0) + 1}?`} confirmLabel="Publicar e exigir novo aceite" onConfirm={publish} onClose={() => setConfirm(false)}>
          <p>A versão {base ? `v${base.version}` : "atual"} deixa de valer e todos os usuários ativos terão o aceite pendente até concordarem com o novo texto.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}
