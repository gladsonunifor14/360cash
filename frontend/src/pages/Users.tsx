import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, post } from "../api";
import { useSession } from "../App";
import { Alert, FieldError, onListKeys, StatusTag, useLoad } from "../components/ui";

type U = { id: string; name: string; email: string; role: "admin" | "contador" | "cliente"; client_id: string | null; last_login_at: string | null; is_active: boolean; created_at: string | null };
type Term = { id: string; kind: string; version: number };
type Acceptance = { user_id: string; term_id: string };

const ROLE: Record<string, { label: string; help: string }> = {
  admin: { label: "Administrador", help: "Acesso total, inclusive usuários, termos, chaves de API e auditoria" },
  contador: { label: "Contador", help: "Opera todas as empresas da carteira" },
  cliente: { label: "Cliente", help: "Vê somente a própria empresa" },
};

type Msg = { kind: "ok" | "error"; text: string } | null;

export default function UsersPage() {
  const { user: me, clients } = useSession();
  const users = useLoad<U[]>(() => api("/users"), []);
  const terms = useLoad<Term[]>(() => api("/terms"), []);
  const acc = useLoad<Acceptance[]>(() => api("/terms/acceptances"), []);
  const [msg, setMsg] = useState<Msg>(null);
  const [roleFilter, setRoleFilter] = useState("");
  const [status, setStatus] = useState("ativos");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<U | null>(null);
  const [confirmOff, setConfirmOff] = useState<U | null>(null);
  const clientName = (id: string | null) => clients.find((c) => c.id === id)?.nome_fantasia ?? clients.find((c) => c.id === id)?.razao_social ?? "—";

  const pendingTerms = useMemo(() => {
    const accepted = new Set((acc.data ?? []).map((a) => `${a.user_id}:${a.term_id}`));
    return (u: U) => (terms.data ?? []).filter((t) => !accepted.has(`${u.id}:${t.id}`)).length;
  }, [acc.data, terms.data]);

  const rows = (users.data ?? []).filter((u) =>
    (!roleFilter || u.role === roleFilter) &&
    (status === "todos" || (status === "ativos") === u.is_active) &&
    (!q || `${u.name} ${u.email}`.toLowerCase().includes(q.toLowerCase())));

  const run = async (fn: () => Promise<string>) => {
    setMsg(null);
    try {
      setMsg({ kind: "ok", text: await fn() });
      users.reload();
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    }
  };

  return (
    <>
      <div className="topbar"><h1 tabIndex={-1} className="grow">Usuários</h1></div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <InviteForm onDone={(t) => { setMsg({ kind: "ok", text: t }); users.reload(); }} />

      <div className="card filters" role="group" aria-label="Filtros">
        <div className="segmented" role="radiogroup" aria-label="Situação">
          {[["ativos", "Ativos"], ["inativos", "Inativos"], ["todos", "Todos"]].map(([v, l]) => (
            <button key={v} role="radio" aria-checked={status === v} className={status === v ? "on" : ""} onClick={() => setStatus(v)}>{l}</button>
          ))}
        </div>
        <select aria-label="Perfil" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="">Todos os perfis</option>
          {Object.entries(ROLE).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
        </select>
        <input type="search" aria-label="Buscar usuário" placeholder="Nome ou e-mail…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className="card">
        <Alert>{users.error}</Alert>
        <table onKeyDown={onListKeys}>
          <thead><tr><th>Usuário</th><th>Perfil</th><th>Empresa</th><th>Situação</th><th>Termos</th><th>Último acesso</th><th>Ações</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="muted">Nenhum usuário neste filtro.</td></tr>}
            {rows.map((u) => {
              const pend = pendingTerms(u);
              return (
                <tr key={u.id}>
                  <td><strong>{u.name}</strong>{u.id === me.id && <span className="muted"> (você)</span>}<div className="muted">{u.email}</div></td>
                  <td><span className="badge" title={ROLE[u.role].help}>{ROLE[u.role].label}</span></td>
                  <td>{u.role === "cliente" ? clientName(u.client_id) : "Todas"}</td>
                  <td>
                    {!u.is_active ? <StatusTag kind="erro" label="Inativo" />
                      : u.last_login_at ? <StatusTag kind="concluido" label="Ativo" />
                        : <StatusTag kind="atencao" label="Convite pendente" />}
                  </td>
                  <td>{pend === 0 ? <StatusTag kind="concluido" label="Aceitos" /> : <StatusTag kind="hoje" label={`${pend} pendente(s)`} />}</td>
                  <td>{u.last_login_at ? new Date(u.last_login_at + "Z").toLocaleString("pt-BR") : "nunca"}</td>
                  <td className="actions">
                    <button data-row className="secondary" onClick={() => setEditing(u)}>Editar</button>
                    {u.is_active && !u.last_login_at && (
                      <button className="secondary" onClick={() => run(async () => (await post<{ detail: string }>(`/users/${u.id}/resend-invite`)).detail)}>Reenviar convite</button>
                    )}
                    {u.id !== me.id && (u.is_active
                      ? <button className="secondary danger" onClick={() => setConfirmOff(u)}>Desativar</button>
                      : <button className="secondary" onClick={() => run(async () => (await post<{ detail: string }>(`/users/${u.id}/reactivate`)).detail)}>Reativar</button>)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="muted">Usuários não são excluídos: desative para bloquear o acesso e preservar a trilha de auditoria.</p>
      </div>

      {editing && <EditDialog user={editing} isMe={editing.id === me.id} onClose={(t) => { setEditing(null); if (t) { setMsg({ kind: "ok", text: t }); users.reload(); } }} />}
      {confirmOff && (
        <ConfirmDialog title={`Desativar ${confirmOff.name}?`} confirmLabel="Desativar usuário"
          onConfirm={() => run(async () => (await post<{ detail: string }>(`/users/${confirmOff.id}/deactivate`)).detail)}
          onClose={() => setConfirmOff(null)}>
          <p>O acesso é bloqueado imediatamente e as sessões abertas são encerradas. O histórico e a auditoria são preservados, e você pode reativar depois.</p>
        </ConfirmDialog>
      )}
    </>
  );
}

function RoleFields({ f, set, errors, inv }: { f: { role: string; client_id: string }; set: (k: string) => (e: React.ChangeEvent<HTMLSelectElement>) => void; errors: Record<string, string>; inv: (k: string) => object }) {
  const { clients } = useSession();
  return (
    <>
      <label htmlFor="f-role">Perfil
        <select {...inv("role")} value={f.role} onChange={set("role")}>
          {Object.entries(ROLE).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
        </select>
        <span className="muted">{ROLE[f.role].help}</span>
        <FieldError id="e-role" msg={errors.role} />
      </label>
      {f.role === "cliente" && (
        <label htmlFor="f-client_id">Empresa
          <select {...inv("client_id")} value={f.client_id} onChange={set("client_id")}>
            <option value="">Selecione a empresa…</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.nome_fantasia || c.razao_social}</option>)}
          </select>
          <FieldError id="e-client_id" msg={errors.client_id} />
        </label>
      )}
    </>
  );
}

function useFieldErrors() {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const inv = (k: string) => ({ id: `f-${k}`, "aria-invalid": !!errors[k] || undefined, "aria-describedby": errors[k] ? `e-${k}` : undefined });
  const fail = (err: unknown) => {
    const ae = err as ApiError;
    setErrors(ae.fields ?? {});
    setError(ae.message);
    const first = Object.keys(ae.fields ?? {})[0];
    if (first) document.getElementById(`f-${first}`)?.focus();
  };
  const reset = () => { setErrors({}); setError(null); };
  return { errors, error, inv, fail, reset };
}

function InviteForm({ onDone }: { onDone: (msg: string) => void }) {
  const [f, setF] = useState({ name: "", email: "", role: "contador", client_id: "" });
  const [busy, setBusy] = useState(false);
  const { errors, error, inv, fail, reset } = useFieldErrors();
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    reset();
    try {
      await post("/users", { ...f, client_id: f.role === "cliente" ? f.client_id || null : null });
      onDone(`Convite enviado para ${f.email}. O usuário recebe um link para definir a senha (válido por 30 minutos).`);
      setF({ name: "", email: "", role: f.role, client_id: f.client_id });
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="card" open>
      <summary><strong>Convidar usuário</strong></summary>
      <Alert>{error}</Alert>
      <form className="form grid3" onSubmit={submit} noValidate>
        <label htmlFor="f-name">Nome<input {...inv("name")} value={f.name} onChange={set("name")} required /><FieldError id="e-name" msg={errors.name} /></label>
        <label htmlFor="f-email">E-mail<input type="email" {...inv("email")} value={f.email} onChange={set("email")} required /><FieldError id="e-email" msg={errors.email} /></label>
        <RoleFields f={f} set={set} errors={errors} inv={inv} />
        <div className="row span-all"><button disabled={busy}>{busy ? "Enviando…" : "Enviar convite"}</button></div>
      </form>
    </details>
  );
}

function EditDialog({ user, isMe, onClose }: { user: U; isMe: boolean; onClose: (msg?: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [f, setF] = useState({ name: user.name, role: user.role as string, client_id: user.client_id ?? "" });
  const { errors, error, inv, fail, reset } = useFieldErrors();
  useEffect(() => { if (!ref.current?.open) ref.current?.showModal(); }, []);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    reset();
    try {
      await api(`/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ ...f, client_id: f.role === "cliente" ? f.client_id || null : null }) });
      onClose(`Usuário ${f.name} atualizado.`);
    } catch (err) {
      fail(err);
    }
  };
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="edit-title" onClose={() => onClose()}>
      <form className="form" onSubmit={save} noValidate>
        <h2 id="edit-title" style={{ margin: 0 }}>Editar {user.email}</h2>
        <Alert>{error}</Alert>
        {isMe && <Alert kind="warn">Você está editando o próprio usuário. Para deixar de ser administrador, peça a outro administrador.</Alert>}
        <label htmlFor="f-name">Nome<input {...inv("name")} value={f.name} onChange={set("name")} autoFocus /><FieldError id="e-name" msg={errors.name} /></label>
        <RoleFields f={f} set={set} errors={errors} inv={inv} />
        <div className="row">
          <button type="submit">Salvar</button>
          <button type="button" className="secondary" onClick={() => ref.current?.close()}>Cancelar (Esc)</button>
        </div>
      </form>
    </dialog>
  );
}

export function ConfirmDialog({ title, confirmLabel, children, onConfirm, onClose }: { title: string; confirmLabel: string; children: React.ReactNode; onConfirm: () => Promise<void> | void; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (!ref.current?.open) ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="confirm-title" onClose={onClose}>
      <form className="form" onSubmit={async (e) => { e.preventDefault(); await onConfirm(); ref.current?.close(); }}>
        <h2 id="confirm-title" style={{ margin: 0 }}>{title}</h2>
        {children}
        <div className="row">
          <button type="submit" autoFocus>{confirmLabel}</button>
          <button type="button" className="secondary" onClick={() => ref.current?.close()}>Voltar (Esc)</button>
        </div>
      </form>
    </dialog>
  );
}
