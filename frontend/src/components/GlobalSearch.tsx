import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../App";

type Hit = { type: string; id: string; client_id: string; client_name: string; label: string; detail: string; route: string };
const TYPE_LABEL: Record<string, string> = { cliente: "Empresa", nota: "Nota fiscal", titulo: "Título", lancamento: "Extrato" };

/** Busca única por CNPJ, nome, valor ou nº de nota. Atalhos: "/" ou Ctrl+K para focar; ↑/↓ e Enter para abrir. */
export default function GlobalSearch() {
  const { setClientId } = useSession();
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName);
      if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      setStatus("");
      return;
    }
    const t = setTimeout(async () => {
      try {
        const r = await api<Hit[]>(`/search?q=${encodeURIComponent(q.trim())}`);
        setHits(r);
        setActive(0);
        setOpen(true);
        setStatus(r.length ? `${r.length} resultado(s)` : "Nenhum resultado");
      } catch (e) {
        setStatus((e as Error).message);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const go = (h: Hit) => {
    setClientId(h.client_id);
    navigate(h.route);
    setOpen(false);
    setQ("");
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(hits.length - 1, a + 1)); setOpen(true); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter" && hits[active]) { e.preventDefault(); go(hits[active]); }
    else if (e.key === "Escape") { setOpen(false); }
  };

  return (
    <div className="search" role="combobox" aria-expanded={open && hits.length > 0} aria-haspopup="listbox" aria-owns="search-results">
      <label htmlFor="global-search" className="sr-only">Busca global</label>
      <input id="global-search" ref={input} type="search" value={q} autoComplete="off"
        placeholder="Buscar CNPJ, fornecedor, valor ou nº da nota  ( / )"
        aria-autocomplete="list" aria-controls="search-results"
        aria-activedescendant={hits[active] ? `hit-${active}` : undefined}
        onChange={(e) => setQ(e.target.value)} onKeyDown={onKeyDown}
        onFocus={() => hits.length && setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      <span className="sr-only" aria-live="polite">{status}</span>
      {open && q.trim().length >= 2 && (
        <ul id="search-results" role="listbox" className="search-results">
          {hits.length === 0 && <li className="muted" role="option" aria-selected="false">{status || "Buscando…"}</li>}
          {hits.map((h, i) => (
            <li key={`${h.type}-${h.id}`} id={`hit-${i}`} role="option" aria-selected={i === active}
              className={i === active ? "active" : undefined} onMouseDown={() => go(h)} onMouseEnter={() => setActive(i)}>
              <span className="badge">{TYPE_LABEL[h.type]}</span>
              <span className="hit-main"><strong>{h.label}</strong><span className="muted">{h.detail}</span></span>
              <span className="muted">{h.client_name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
