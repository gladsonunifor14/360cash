import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, Client, logout, onSessionEnd, tryRestoreSession, User } from "./api";
import { ForgotPage, LoginPage, RegisterPage, ResetPage } from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import ClientsPage from "./pages/Clients";
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

export function ClientPicker() {
  const { clients, clientId, setClientId, user } = useSession();
  if (user.role === "cliente") return <strong>{clients[0]?.razao_social}</strong>;
  return (
    <select value={clientId} onChange={(e) => setClientId(e.target.value)} aria-label="Empresa cliente">
      {clients.length === 0 && <option value="">Cadastre um cliente</option>}
      {clients.map((c) => (
        <option key={c.id} value={c.id}>{c.nome_fantasia || c.razao_social}</option>
      ))}
    </select>
  );
}

function Shell({ user, onExit }: { user: User; onExit: () => void }) {
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  const staff = user.role !== "cliente";

  const reloadClients = async () => {
    const list = await api<Client[]>("/clients");
    setClients(list);
    setClientId((cur) => (list.some((c) => c.id === cur) ? cur : list[0]?.id ?? ""));
  };
  useEffect(() => {
    reloadClients();
  }, []);

  const links: [string, string, boolean][] = [
    ["/", "Painel BI", true],
    ["/clientes", "Clientes", staff],
    ["/notas", "Notas fiscais", true],
    ["/extratos", "Extratos bancários", true],
    ["/aplicacoes", "Aplicações", true],
    ["/relatorios", "Relatórios", true],
    ["/contratos", "Contratos e LGPD", true],
    ["/documentos", "Documentos", true],
    ["/auditoria", "Auditoria", user.role === "admin"],
    ["/conta", "Minha conta", true],
  ];

  return (
    <SessionCtx.Provider value={{ user, clients, clientId, setClientId, reloadClients }}>
      <div className="layout">
        <nav className="sidebar">
          <div className="brand">360<span>cash</span></div>
          {links.filter(([, , show]) => show).map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>{label}</NavLink>
          ))}
          <div className="spacer" />
          <a href="#" onClick={(e) => { e.preventDefault(); onExit(); }}>Sair ({user.name.split(" ")[0]})</a>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
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
