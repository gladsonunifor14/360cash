import { useState } from "react";
import { api, Header, money, pct } from "../api";
import { useSession } from "../App";
import { Alert, Bars, defaultPeriod, Money, PeriodPicker, ReportHeader, useLoad } from "../components/ui";

type Management = {
  cabecalho: Header;
  indicadores: Record<string, number | string | null>;
  top_clientes: { nome: string; documento: string; valor: string; notas: number }[];
  top_fornecedores: { nome: string; documento: string; valor: string; notas: number }[];
  top_despesas: { conta: string; valor: string }[];
  receita_mensal: Record<string, string>;
  lucro_mensal: Record<string, string>;
  caixa_mensal: Record<string, string>;
};

const KPIS: [string, string, "money" | "pct" | "int"][] = [
  ["faturamento", "Faturamento", "money"],
  ["lucro_liquido", "Lucro líquido", "money"],
  ["margem_liquida_pct", "Margem líquida", "pct"],
  ["margem_bruta_pct", "Margem bruta", "pct"],
  ["geracao_caixa", "Geração de caixa", "money"],
  ["ticket_medio", "Ticket médio", "money"],
  ["compras", "Compras", "money"],
  ["rendimento_aplicacoes_liquido", "Rendimento líquido aplicações", "money"],
  ["lancamentos_pendentes", "Lançamentos a classificar", "int"],
];

export default function Dashboard() {
  const { clientId } = useSession();
  const [period, setPeriod] = useState(defaultPeriod());
  const { data, error, loading } = useLoad<Management | null>(
    () => (clientId ? api<Management>(`/clients/${clientId}/reports/management?start=${period.start}&end=${period.end}`) : Promise.resolve(null)),
    [clientId, period.start, period.end],
  );
  const fmt = (v: number | string | null, kind: string) =>
    kind === "money" ? money(v) : kind === "pct" ? pct(v) : String(v ?? 0);

  return (
    <>
      <div className="topbar">
        <h1 tabIndex={-1} className="grow">Indicadores (BI)</h1>
        <PeriodPicker value={period} onChange={setPeriod} />
        <button className="secondary" onClick={() => window.print()}>Imprimir / PDF</button>
      </div>
      <Alert>{error}</Alert>
      {loading && <p className="muted">Carregando…</p>}
      {data && (
        <div className="card">
          <ReportHeader h={data.cabecalho} />
          {Number(data.indicadores.lancamentos_pendentes) > 0 && (
            <Alert kind="warn">
              {String(data.indicadores.lancamentos_pendentes)} lançamentos bancários aguardam classificação
              ({money(data.indicadores.valor_pendente_classificacao)}). Os relatórios ficam mais precisos após classificá-los.
            </Alert>
          )}
          <div className="grid">
            {KPIS.map(([k, label, kind]) => (
              <div className="card kpi" key={k}>
                <div className="label">{label}</div>
                <div className={`value ${Number(data.indicadores[k]) < 0 ? "neg" : ""}`}>{fmt(data.indicadores[k], kind)}</div>
              </div>
            ))}
          </div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
            <div className="card"><h2>Receita bruta mensal</h2><Bars series={data.receita_mensal} /></div>
            <div className="card"><h2>Lucro líquido mensal</h2><Bars series={data.lucro_mensal} /></div>
            <div className="card"><h2>Geração de caixa mensal</h2><Bars series={data.caixa_mensal} /></div>
          </div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
            <Ranking title="Maiores clientes" rows={data.top_clientes.map((r) => [r.nome || r.documento, r.valor])} />
            <Ranking title="Maiores fornecedores" rows={data.top_fornecedores.map((r) => [r.nome || r.documento, r.valor])} />
            <Ranking title="Maiores despesas (caixa)" rows={data.top_despesas.map((r) => [r.conta, r.valor])} />
          </div>
        </div>
      )}
    </>
  );
}

function Ranking({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {rows.length === 0 ? <p className="muted">Sem dados no período.</p> : (
        <table className="ranking"><tbody>{rows.map(([n, v], i) => <tr key={i}><td>{n}</td><td className="num"><Money v={v} /></td></tr>)}</tbody></table>
      )}
    </div>
  );
}
