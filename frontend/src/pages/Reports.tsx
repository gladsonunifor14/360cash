import { Fragment, useState } from "react";
import { api, Header, pct } from "../api";
import { ClientPicker, useSession } from "../App";
import { Alert, defaultPeriod, Money, PeriodPicker, ReportHeader, useLoad } from "../components/ui";

type Values = Record<string, string>;
type Conta = { conta: string; valores: Values; total: string };
type Dre = {
  cabecalho: Header; meses: string[]; margens: Record<string, string | null>;
  linhas: { chave: string; descricao: string; tipo: string; valores: Values; total: string; contas: Conta[] }[];
};
type CashFlow = {
  cabecalho: Header; meses: string[];
  grupos: { grupo: string; nome: string; contas: Conta[]; valores: Values; total: string }[];
  entradas: Values; saidas: Values; geracao_caixa: Values; geracao_acumulada: Values;
};

const monthLabel = (m: string) => `${m.slice(5)}/${m.slice(0, 4)}`;

export default function ReportsPage() {
  const { clientId } = useSession();
  const [tab, setTab] = useState<"dre" | "fc">("dre");
  const [regime, setRegime] = useState("competencia");
  const [period, setPeriod] = useState(defaultPeriod());
  const q = `start=${period.start}&end=${period.end}`;
  const { data, error, loading } = useLoad<Dre | CashFlow | null>(
    () => !clientId ? Promise.resolve(null)
      : tab === "dre" ? api(`/clients/${clientId}/reports/dre?${q}&regime=${regime}`)
        : api(`/clients/${clientId}/reports/cash-flow?${q}`),
    [clientId, tab, regime, period.start, period.end],
  );

  return (
    <>
      <div className="topbar">
        <h1 className="grow" style={{ margin: 0 }}>Relatórios</h1>
        <ClientPicker />
        <select value={tab} onChange={(e) => setTab(e.target.value as "dre" | "fc")} aria-label="Relatório">
          <option value="dre">DRE gerencial</option>
          <option value="fc">Fluxo de caixa</option>
        </select>
        {tab === "dre" && (
          <select value={regime} onChange={(e) => setRegime(e.target.value)} aria-label="Regime">
            <option value="competencia">Competência</option>
            <option value="caixa">Caixa</option>
          </select>
        )}
        <PeriodPicker value={period} onChange={setPeriod} />
        <button className="secondary" onClick={() => window.print()}>Imprimir / PDF</button>
      </div>
      <Alert>{error}</Alert>
      {loading && <p className="muted">Carregando…</p>}
      {data && (
        <div className="card">
          <ReportHeader h={data.cabecalho} />
          {"linhas" in data ? <DreTable d={data} /> : <CashFlowTable d={data} />}
        </div>
      )}
    </>
  );
}

function DreTable({ d }: { d: Dre }) {
  return (
    <>
      <table>
        <thead><tr><th>Descrição</th>{d.meses.map((m) => <th key={m} className="num">{monthLabel(m)}</th>)}<th className="num">Total</th></tr></thead>
        <tbody>
          {d.linhas.map((l) => (
            <Fragment key={l.chave}>
              <tr className={l.tipo}>
                <td>{l.descricao}</td>
                {d.meses.map((m) => <td key={m} className="num"><Money v={l.valores[m]} /></td>)}
                <td className="num"><Money v={l.total} /></td>
              </tr>
              {l.contas.map((c) => (
                <tr key={`${l.chave}-${c.conta}`} className="conta">
                  <td>{c.conta}</td>
                  {d.meses.map((m) => <td key={m} className="num"><Money v={c.valores[m]} /></td>)}
                  <td className="num"><Money v={c.total} /></td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
      <p className="muted">Margem bruta {pct(d.margens.bruta_pct)} · operacional {pct(d.margens.operacional_pct)} · líquida {pct(d.margens.liquida_pct)}</p>
    </>
  );
}

function CashFlowTable({ d }: { d: CashFlow }) {
  const row = (label: string, v: Values, cls = "subtotal") => (
    <tr className={cls}><td>{label}</td>{d.meses.map((m) => <td key={m} className="num"><Money v={v[m]} /></td>)}<td /></tr>
  );
  return (
    <table>
      <thead><tr><th>Descrição</th>{d.meses.map((m) => <th key={m} className="num">{monthLabel(m)}</th>)}<th className="num">Total</th></tr></thead>
      <tbody>
        {d.grupos.map((g) => (
          <Fragment key={g.grupo}>
            <tr className="subtotal">
              <td>{g.nome}</td>{d.meses.map((m) => <td key={m} className="num"><Money v={g.valores[m]} /></td>)}<td className="num"><Money v={g.total} /></td>
            </tr>
            {g.contas.map((c) => (
              <tr key={`${g.grupo}-${c.conta}`} className="conta">
                <td>{c.conta}</td>{d.meses.map((m) => <td key={m} className="num"><Money v={c.valores[m]} /></td>)}<td className="num"><Money v={c.total} /></td>
              </tr>
            ))}
          </Fragment>
        ))}
        {row("Entradas", d.entradas)}
        {row("Saídas", d.saidas)}
        {row("Geração de caixa do mês", d.geracao_caixa, "resultado")}
        {row("Geração de caixa acumulada", d.geracao_acumulada, "resultado")}
      </tbody>
    </table>
  );
}
