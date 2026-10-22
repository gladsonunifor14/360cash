import { FormEvent, useState } from "react";
import { cnpjMask, post } from "../api";
import { useSession } from "../App";
import { Alert } from "../components/ui";

export default function ClientsPage() {
  const { clients, reloadClients, setClientId } = useSession();
  const [cnpj, setCnpj] = useState("");
  const [regime, setRegime] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const c = await post<{ id: string; razao_social: string }>("/clients", { cnpj, regime_tributario: regime || null });
      setMsg({ kind: "ok", text: `${c.razao_social} cadastrado com dados da Receita Federal.` });
      setCnpj("");
      await reloadClients();
      setClientId(c.id);
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h1 tabIndex={-1}>Clientes</h1>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Novo cliente</h2>
        {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
        <form className="row" onSubmit={add}>
          <label>CNPJ<input value={cnpj} onChange={(e) => setCnpj(e.target.value)} placeholder="00.000.000/0000-00" required /></label>
          <label>
            Regime tributário
            <select value={regime} onChange={(e) => setRegime(e.target.value)}>
              <option value="">Detectar pela Receita</option>
              <option value="mei">MEI</option>
              <option value="simples">Simples Nacional</option>
              <option value="presumido">Lucro Presumido</option>
              <option value="real">Lucro Real</option>
            </select>
          </label>
          <button disabled={busy}>{busy ? "Consultando Receita…" : "Buscar e cadastrar"}</button>
        </form>
      </div>
      <div className="card">
        <table>
          <thead><tr><th>Razão social</th><th>CNPJ</th><th>Regime</th><th>Situação</th><th>Município/UF</th><th>CNAE</th></tr></thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.id}>
                <td>{c.razao_social}{c.nome_fantasia && <div className="muted">{c.nome_fantasia}</div>}</td>
                <td>{cnpjMask(c.cnpj)}</td>
                <td>{c.regime_tributario ?? "—"}</td>
                <td><span className="badge">{c.situacao_cadastral ?? "—"}</span></td>
                <td>{c.endereco ? `${c.endereco.municipio ?? ""}/${c.endereco.uf ?? ""}` : "—"}</td>
                <td className="muted">{c.cnae_principal ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
