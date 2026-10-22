import { FormEvent, useState } from "react";
import { api, dateBR, money, pct, post } from "../api";
import { ClientPicker, useSession } from "../App";
import { Alert, Money, useLoad } from "../components/ui";
import { NewAccount } from "./Banking";

type Account = { id: string; kind: string; bank_name: string; product_name: string | null };
type Stmt = Record<string, string | null> & { id: string; bank_account_id: string; competencia: string };

const FIELDS: [string, string][] = [
  ["saldo_inicial", "Saldo inicial"], ["aplicacoes", "Aplicações"], ["resgates", "Resgates (líquido)"],
  ["saldo_final", "Saldo final"], ["irrf", "IRRF"], ["iof", "IOF"], ["taxa_administracao", "Taxa de administração"],
  ["benchmark_mes_pct", "CDI do mês (%)"],
];

export default function InvestmentsPage() {
  const { clientId } = useSession();
  const accounts = useLoad<Account[]>(() => (clientId ? api(`/clients/${clientId}/bank-accounts`) : Promise.resolve([])), [clientId]);
  const stmts = useLoad<Stmt[]>(() => (clientId ? api(`/clients/${clientId}/investments`) : Promise.resolve([])), [clientId]);
  const [f, setF] = useState<Record<string, string>>({ bank_account_id: "", competencia: "" });
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [sim, setSim] = useState({ valor_aplicado: "", valor_resgate_bruto: "", data_aplicacao: "", data_resgate: "" });
  const [simOut, setSimOut] = useState<Record<string, string | number> | null>(null);
  const invAccounts = accounts.data?.filter((a) => a.kind === "aplicacao") ?? [];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
      const r = await post<Stmt>("/investments", body);
      setMsg({ kind: "ok", text: `Rendimento líquido do mês: ${money(r.rendimento_liquido)} (${pct(r.taxa_liquida_pct)})` });
      stmts.reload();
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    }
  };
  const simulate = async (e: FormEvent) => {
    e.preventDefault();
    try {
      setSimOut(await post("/investments/simulate-ir", sim));
    } catch (err) {
      setMsg({ kind: "error", text: (err as Error).message });
    }
  };
  const accName = (id: string) => {
    const a = accounts.data?.find((x) => x.id === id);
    return a ? `${a.bank_name} ${a.product_name ?? ""}` : "";
  };

  return (
    <>
      <div className="topbar"><h1 className="grow" style={{ margin: 0 }}>Aplicações financeiras</h1><ClientPicker /></div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Extrato mensal</h2>
        <form className="row" onSubmit={submit}>
          <label>Aplicação
            <select value={f.bank_account_id} onChange={(e) => setF({ ...f, bank_account_id: e.target.value })} required>
              <option value="">Selecione</option>
              {invAccounts.map((a) => <option key={a.id} value={a.id}>{a.bank_name} {a.product_name}</option>)}
            </select>
          </label>
          <label>Mês<input type="month" onChange={(e) => setF({ ...f, competencia: `${e.target.value}-01` })} required /></label>
          {FIELDS.map(([k, label]) => (
            <label key={k}>{label}<input inputMode="decimal" size={10} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value.replace(",", ".") })} /></label>
          ))}
          <button>Calcular e salvar</button>
        </form>
        <NewAccount clientId={clientId} kind="aplicacao" onDone={accounts.reload} />
      </div>
      <div className="card">
        <table>
          <thead><tr><th>Mês</th><th>Aplicação</th><th className="num">Saldo final</th><th className="num">Rend. bruto</th><th className="num">IRRF</th><th className="num">Taxa adm.</th><th className="num">Rend. líquido</th><th className="num">Taxa bruta</th><th className="num">Taxa líquida</th><th className="num">% CDI</th></tr></thead>
          <tbody>
            {stmts.data?.map((s) => (
              <tr key={s.id}>
                <td>{dateBR(s.competencia).slice(3)}</td><td>{accName(s.bank_account_id)}</td>
                <td className="num"><Money v={s.saldo_final} /></td><td className="num"><Money v={s.rendimento_bruto} /></td>
                <td className="num"><Money v={s.irrf} /></td><td className="num"><Money v={s.taxa_administracao} /></td>
                <td className="num"><Money v={s.rendimento_liquido} /></td><td className="num">{pct(s.taxa_bruta_pct)}</td>
                <td className="num">{pct(s.taxa_liquida_pct)}</td><td className="num">{pct(s.pct_benchmark)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Simulador de IRRF e IOF no resgate (tabela regressiva)</h2>
        <form className="row" onSubmit={simulate}>
          <label>Valor aplicado<input value={sim.valor_aplicado} onChange={(e) => setSim({ ...sim, valor_aplicado: e.target.value })} required /></label>
          <label>Valor bruto no resgate<input value={sim.valor_resgate_bruto} onChange={(e) => setSim({ ...sim, valor_resgate_bruto: e.target.value })} required /></label>
          <label>Data aplicação<input type="date" value={sim.data_aplicacao} onChange={(e) => setSim({ ...sim, data_aplicacao: e.target.value })} required /></label>
          <label>Data resgate<input type="date" value={sim.data_resgate} onChange={(e) => setSim({ ...sim, data_resgate: e.target.value })} required /></label>
          <button>Simular</button>
        </form>
        {simOut && (
          <p>{simOut.dias} dias · rendimento {money(simOut.rendimento_bruto)} · IOF {money(simOut.iof)} · alíquota IR {pct(simOut.aliquota_ir_pct)} · IRRF {money(simOut.irrf)} · <strong>líquido {money(simOut.valor_liquido)}</strong></p>
        )}
      </div>
    </>
  );
}
