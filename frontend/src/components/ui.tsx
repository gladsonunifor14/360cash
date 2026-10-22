import { ReactNode, useCallback, useEffect, useState } from "react";
import { Header, money } from "../api";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fn());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}

export function Alert({ kind = "error", children }: { kind?: "error" | "ok" | "warn"; children: ReactNode }) {
  if (!children) return null;
  return <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

const today = new Date();
const iso = (d: Date) => d.toISOString().slice(0, 10);
export const defaultPeriod = () => ({
  start: iso(new Date(today.getFullYear(), 0, 1)),
  end: iso(new Date(today.getFullYear(), today.getMonth() + 1, 0)),
});

export function PeriodPicker({ value, onChange }: { value: { start: string; end: string }; onChange: (v: { start: string; end: string }) => void }) {
  return (
    <>
      <input type="date" aria-label="Início" value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} />
      <input type="date" aria-label="Fim" value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })} />
    </>
  );
}

export function Money({ v }: { v: number | string | null | undefined }) {
  const n = Number(v ?? 0);
  return <span className={n < 0 ? "neg" : undefined}>{money(n)}</span>;
}

export function ReportHeader({ h }: { h: Header }) {
  return (
    <div className="report-header">
      <div>
        <strong style={{ fontSize: "1.15rem" }}>{h.titulo}</strong>
        <div>{h.empresa.razao_social} · CNPJ {h.empresa.cnpj}</div>
        <div className="muted">Período: {h.periodo.inicio.split("-").reverse().join("/")} a {h.periodo.fim.split("-").reverse().join("/")}</div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="muted">Elaborado por</div>
        <strong>{h.elaborado_por.razao_social}</strong>
        <div className="muted">
          CNPJ {h.elaborado_por.cnpj}
          {h.elaborado_por.crc && ` · CRC ${h.elaborado_por.crc}`}
        </div>
        {h.elaborado_por.responsavel_tecnico && <div className="muted">Resp. técnico: {h.elaborado_por.responsavel_tecnico}</div>}
      </div>
    </div>
  );
}

export function Bars({ series }: { series: Record<string, number | string> }) {
  const entries = Object.entries(series);
  const max = Math.max(1, ...entries.map(([, v]) => Math.abs(Number(v))));
  return (
    <div className="bars" role="img" aria-label="Gráfico mensal">
      {entries.map(([k, v]) => (
        <div className="bar" key={k} title={`${k}: ${money(v)}`}>
          <div className={Number(v) < 0 ? "neg" : undefined} style={{ height: `${(Math.abs(Number(v)) / max) * 100}%` }} />
          {k.slice(5)}/{k.slice(2, 4)}
        </div>
      ))}
    </div>
  );
}
