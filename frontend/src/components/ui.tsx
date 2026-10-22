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

// ------------------------------------------------------------------ status acessível: cor + ícone + texto

type StatusKind = "atrasado" | "hoje" | "concluido" | "proximo" | "atencao" | "ativo" | "reautenticar" | "erro" | "manual";

const STATUS: Record<StatusKind, { label: string; tone: "danger" | "warning" | "success" | "neutral"; icon: ReactNode }> = {
  atrasado: { label: "Atrasado", tone: "danger", icon: <path d="M8 1.5 15 14.5H1L8 1.5Zm0 4.5v4m0 2v.5" /> },
  hoje: { label: "Para hoje", tone: "warning", icon: <><circle cx="8" cy="8" r="6.5" /><path d="M8 4.5V8l2.5 1.5" /></> },
  concluido: { label: "Concluído", tone: "success", icon: <><circle cx="8" cy="8" r="6.5" /><path d="m5 8.2 2 2 4-4.2" /></> },
  proximo: { label: "No prazo", tone: "neutral", icon: <path d="M3 8h9m-3-3.5L12.5 8 9 11.5" /> },
  atencao: { label: "Atenção", tone: "warning", icon: <><circle cx="8" cy="8" r="6.5" /><path d="M8 4.5v4.5m0 2v.5" /></> },
  ativo: { label: "Conectado", tone: "success", icon: <><circle cx="8" cy="8" r="6.5" /><path d="m5 8.2 2 2 4-4.2" /></> },
  reautenticar: { label: "Reautenticar", tone: "warning", icon: <path d="M13 3v3.5H9.5M13 6.5A5.5 5.5 0 1 0 13.5 10" /> },
  erro: { label: "Falha", tone: "danger", icon: <><circle cx="8" cy="8" r="6.5" /><path d="m5.5 5.5 5 5m0-5-5 5" /></> },
  manual: { label: "Importação manual", tone: "neutral", icon: <path d="M8 2.5v8m-3-3 3 3 3-3M3 13.5h10" /> },
};

export function StatusTag({ kind, label, count }: { kind: string; label?: string; count?: number }) {
  const s = STATUS[kind as StatusKind] ?? { label: kind, tone: "neutral" as const, icon: null };
  return (
    <span className={`tag tag-${s.tone}`}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{s.icon}</svg>
      {count !== undefined && <strong>{count}</strong>}
      {label ?? s.label}
    </span>
  );
}

// ------------------------------------------------------------------ navegação por teclado em listas

/** Setas ↑/↓ movem o foco entre linhas (data-row), Home/End vão ao início/fim. */
export function onListKeys(e: React.KeyboardEvent<HTMLElement>) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
  const target = e.target as HTMLElement;
  if (target.tagName === "INPUT" && (target as HTMLInputElement).type !== "checkbox") return;
  if (target.tagName === "SELECT" || target.tagName === "TEXTAREA") return;
  const rows = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[data-row]"));
  if (!rows.length) return;
  const current = rows.findIndex((r) => r === document.activeElement || r.contains(document.activeElement));
  const next = e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1
    : Math.min(rows.length - 1, Math.max(0, current + (e.key === "ArrowDown" ? 1 : -1)));
  e.preventDefault();
  rows[next].focus();
}

export function FieldError({ msg, id }: { msg?: string; id: string }) {
  return msg ? <span id={id} className="field-error" role="alert">{msg}</span> : null;
}
