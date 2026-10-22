import { createContext, useContext, useEffect, useRef, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, Client, logout, onSessionEnd, tryRestoreSession, User } from "./api";
import GlobalSearch from "./components/GlobalSearch";
import { ForgotPage, LoginPage, RegisterPage, ResetPage } from "./pages/Auth";
import ControlTower from "./pages/ControlTower";
import Dashboard from "./pages/Dashboard";
import ClientsPage from "./pages/Clients";
import PayablesPage from "./pages/Payables";
import ReconciliationPage from "./pages/Reconciliation";
import InvoicesPage from "./pages/Invoices";
import BankingPage from "./pages/Banking";
import InvestmentsPage from "./pages/Investments";
import ReportsPage from "./pages/Reports";
import CompliancePage from "./pages/Compliance";
import DocumentsPage from "./pages/Documents";
import SettingsPage from "./pages/Settings";
import AuditPage from "./pages/Audit";

type Session = {
  user: User;
  clients: Client[];
  clientId: string;
  setClientId: (id: string) => void;
  reloadClients: () => Promise<void>;
};
const SessionCtx = createContext<Session | null>(null);
export const useSession = () => useContext(SessionCtx)!;

const CLIENT_KEY = "c360.client";
const RECENT_KEY = "c360.recent";
const read = (k: string, store: Storage) => {
  try {
    return store.getItem(k);
  } catch {
    return null;
  }
};
const write = (k: string, v: string, store: Storage) => {
  try {
    store.setItem(k, v);
  } catch {
    /* armazenamento indisponível: segue sem lembrar */
  }
};

/** Mantido para compatibilidade: a troca de empresa agora fica no cabeçalho global. */
export function ClientPicker() {
  return null;
}

function CompanySwitcher() {
  const { clients, clientId, setClientId, user } = useSession();
  const [recent, setRecent] = useState<string[]>(() => JSON.parse(read(RECENT_KEY, localStorage) ?? "[]"));
  useEffect(() => {
    if (!clientId) return;
    setRecent((r) => {
      const next = [clientId, ...r.filter((x) => x !== clientId)].slice(0, 5);
      write(RECENT_KEY, JSON.stringify(next), localStorage);
      return next;
    });
  }, [clientId]);

  // Alt+1..5 troca para as empresas recentes sem tirar a mão do teclado
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || !/^[1-5]$/.test(e.key)) return;
      const id = recent[Number(e.key) - 1];
      if (id && clients.some((c) => c.id === id)) {
        e.preventDefault();
        setClientId(id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [recent, clients, setClientId]);

  if (user.role === "cliente") return <strong>{clients[0]?.razao_social}</strong>;
  const name = (id: string) => {
    const c = clients.find((x) => x.id === id);
    return c ? c.nome_fantasia || c.razao_social : null;
  };
  return (
    <div className="switcher">
      <label className="sr-only" htmlFor="company">Empresa em atendimento</label>
      <select id="company" value={clientId} onChange={(e) => setClientId(e.target.value)}>
        {clients.length === 0 && <option value="">Cadastre um cliente</option>}
        {clients.map((c) => <option key={c.id} value={c.id}>{c.nome_fantasia || c.razao_social}</option>)}
      </select>
      <div className="chips" aria-label="Empresas recentes">
        {recent.filter((id) => id !== clientId && name(id)).slice(0, 4).map((id) => (
          <button key={id} className="chip" onClick={() => setClientId(id)}
            title={`Alt+${recent.indexOf(id) + 1}`}>{name(id)}</button>
        ))}
      </div>
    </div>
  );
}

function Shell({ user, onExit }: { user: User; onExit: () => void }) {
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientIdState] = useState(() => read(CLIENT_KEY, sessionStorage) ?? "");
  const staff = user.role !== "cliente";
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  const setClientId = (id: string) => {
    setClientIdState(id);
    write(CLIENT_KEY, id, sessionStorage);
  };
  const reloadClients = async () => {
    const list = await api<Client[]>("/clients");
    setClients(list);
    setClientIdState((cur) => (list.some((c) => c.id === cur) ? cur : list[0]?.id ?? ""));
  };
  useEffect(() => {
    reloadClients();
  }, []);
  useEffect(() => {
    mainRef.current?.querySelector("h1")?.focus();
  }, [location.pathname]);

  const links: [string, string, boolean][] = [
    ["/", "Torre de controle", true],
    ["/financeiro", "Contas a pagar e receber", true],
    ["/conciliacao", "Conciliação bancária", true],
    ["/extratos", "Extratos e classificação", true],
    ["/notas", "Notas fiscais", true],
    ["/aplicacoes", "Aplicações", true],
    ["/bi", "Indicadores (BI)", true],
    ["/relatorios", "DRE e Fluxo de caixa", true],
    ["/clientes", "Clientes", staff],
    ["/contratos", "Contratos e LGPD", true],
    ["/documentos", "Documentos", true],
    ["/auditoria", "Auditoria", user.role === "admin"],
    ["/conta", "Minha conta", true],
  ];

  return (
    <SessionCtx.Provider value={{ user, clients, clientId, setClientId, reloadClients }}>
      <a href="#conteudo" className="skip">Pular para o conteúdo</a>
      <div className="layout">
        <nav className="sidebar" aria-label="Menu principal">
          <div className="brand">360<span>cash</span></div>
          {links.filter(([, , show]) => show).map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>{label}</NavLink>
          ))}
          <div className="spacer" />
          <a href="#" onClick={(e) => { e.preventDefault(); onExit(); }}>Sair ({user.name.split(" ")[0]})</a>
        </nav>
        <div className="workspace">
          <header className="appbar">
            <CompanySwitcher />
            <GlobalSearch />
          </header>
          <main className="main" id="conteudo" ref={mainRef}>
            <Routes>
              <Route path="/" element={<ControlTower />} />
              <Route path="/financeiro" element={<PayablesPage />} />
              <Route path="/conciliacao" element={<ReconciliationPage />} />
              <Route path="/bi" element={<Dashboard />} />
              <Route path="/painel" element={<Navigate to="/bi" replace />} />
              <Route path="/clientes" element={<ClientsPage />} />
              <Route path="/notas" element={<InvoicesPage />} />
              <Route path="/extratos" element={<BankingPage />} />
              <Route path="/aplicacoes" element={<InvestmentsPage />} />
              <Route path="/relatorios" element={<ReportsPage />} />
              <Route path="/contratos" element={<CompliancePage />} />
              <Route path="/documentos" element={<DocumentsPage />} />
              <Route path="/auditoria" element={<AuditPage />} />
              <Route path="/conta" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </main>
        </div>
      </div>
    </SessionCtx.Provider>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const loadUser = async () => setUser(await api<User>("/auth/me"));
  const exit = async () => {
    await logout();
    setUser(null);
    navigate("/login");
  };

  useEffect(() => {
    onSessionEnd(() => setUser(null));
    tryRestoreSession()
      .then((ok) => (ok ? loadUser() : undefined))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="auth-page">Carregando…</div>;
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage onLogged={loadUser} />} />
        <Route path="/cadastro" element={<RegisterPage />} />
        <Route path="/esqueci-senha" element={<ForgotPage />} />
        <Route path="/redefinir-senha" element={<ResetPage />} />
        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    );
  }
  return <Shell user={user} onExit={exit} />;
}
