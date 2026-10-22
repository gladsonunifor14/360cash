import { FormEvent, useState } from "react";
import { api, dateBR, post } from "../api";
import { useSession } from "../App";
import { Alert, useLoad } from "../components/ui";

type Key = { id: string; name: string; prefix: string; created_at: string; revoked_at: string | null; last_used_at: string | null };

export default function SettingsPage() {
  const { user } = useSession();
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const change = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await post<{ detail: string }>("/auth/password/change", pw);
      setMsg({ kind: "ok", text: r.detail });
      setPw({ current_password: "", new_password: "" });
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    }
  };

  return (
    <>
      <h1 tabIndex={-1}>Minha conta</h1>
      <div className="card">
        <p><strong>{user.name}</strong> · {user.email} · <span className="badge">{user.role}</span></p>
        <h2>Alterar senha</h2>
        {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
        <form className="row" onSubmit={change}>
          <label>Senha atual<input type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required /></label>
          <label>Nova senha<input type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required /></label>
          <button>Alterar</button>
        </form>
      </div>
      {user.role === "admin" && <ApiKeys />}
    </>
  );
}

function ApiKeys() {
  const keys = useLoad<Key[]>(() => api("/api-keys"), []);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const create = async (e: FormEvent) => {
    e.preventDefault();
    const r = await post<{ key: string }>("/api-keys", { name });
    setCreated(r.key);
    setName("");
    keys.reload();
  };
  const revoke = async (id: string) => {
    await api(`/api-keys/${id}`, { method: "DELETE" });
    keys.reload();
  };
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Integrações via API</h2>
      <p className="muted">Documentação: <a href="/docs" target="_blank" rel="noreferrer">Swagger</a>. Envie a chave no header <code>X-API-Key</code>.</p>
      {created && <Alert kind="warn">Copie agora, ela não será exibida novamente: <code>{created}</code></Alert>}
      <form className="row" onSubmit={create}>
        <label>Nome da integração<input value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <button>Gerar chave</button>
      </form>
      <table style={{ marginTop: "1rem" }}>
        <thead><tr><th>Nome</th><th>Prefixo</th><th>Criada</th><th>Último uso</th><th /></tr></thead>
        <tbody>
          {keys.data?.map((k) => (
            <tr key={k.id} style={k.revoked_at ? { opacity: .5 } : undefined}>
              <td>{k.name}</td><td><code>{k.prefix}…</code></td><td>{dateBR(k.created_at)}</td><td>{dateBR(k.last_used_at)}</td>
              <td>{k.revoked_at ? "revogada" : <button className="secondary" onClick={() => revoke(k.id)}>Revogar</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
