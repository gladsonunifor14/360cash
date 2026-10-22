import { FormEvent, ReactNode, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { post, setSession } from "../api";
import { Alert } from "../components/ui";

function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="brand">360<span>cash</span></div>
        <p className="muted">BPO Financeiro para escritórios de contabilidade</p>
        <h1>{title}</h1>
        {children}
      </div>
    </div>
  );
}

function useSubmit() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = (fn: () => Promise<void>) => async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run, setError };
}

export function LoginPage({ onLogged }: { onLogged: () => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpToken, setOtpToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [info, setInfo] = useState<string | null>(null);
  const { error, busy, run } = useSubmit();
  const navigate = useNavigate();

  const step1 = run(async () => {
    const r = await post<{ otp_token: string; message: string }>("/auth/login", { email, password });
    setOtpToken(r.otp_token);
    setInfo(r.message);
    setPassword("");
  });
  const step2 = run(async () => {
    setSession(await post("/auth/otp/verify", { otp_token: otpToken, code }));
    await onLogged();
    navigate("/");
  });
  const resend = run(async () => {
    const r = await post<{ otp_token: string; message: string }>("/auth/otp/resend", { otp_token: otpToken });
    setOtpToken(r.otp_token);
    setInfo(r.message);
  });

  if (otpToken) {
    return (
      <AuthCard title="Código de verificação">
        <Alert kind="ok">{info}</Alert>
        <Alert>{error}</Alert>
        <form className="form" onSubmit={step2}>
          <label>
            Código de 6 dígitos enviado para {email}
            <input className="otp" inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="\d{6}"
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} autoFocus required />
          </label>
          <button disabled={busy || code.length !== 6}>Entrar</button>
          <button type="button" className="secondary" onClick={resend} disabled={busy}>Reenviar código</button>
        </form>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Entrar">
      <Alert>{error}</Alert>
      <form className="form" onSubmit={step1}>
        <label>E-mail<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Senha<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button disabled={busy}>Continuar</button>
      </form>
      <p className="muted">
        <Link to="/esqueci-senha">Esqueci minha senha</Link> · <Link to="/cadastro">Cadastrar escritório</Link>
      </p>
    </AuthCard>
  );
}

export function RegisterPage() {
  const [f, setF] = useState({ office_cnpj: "", name: "", email: "", password: "", crc: "", accept_terms: false });
  const [done, setDone] = useState<string | null>(null);
  const { error, busy, run } = useSubmit();
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const submit = run(async () => {
    const r = await post<{ detail: string }>("/auth/register", { ...f, crc: f.crc || null });
    setDone(r.detail);
  });
  return (
    <AuthCard title="Cadastro do escritório">
      <Alert>{error}</Alert>
      {done ? (
        <>
          <Alert kind="ok">{done}</Alert>
          <Link to="/login">Ir para o login</Link>
        </>
      ) : (
        <form className="form" onSubmit={submit}>
          <label>CNPJ do escritório (dados importados da Receita Federal)<input value={f.office_cnpj} onChange={set("office_cnpj")} required /></label>
          <label>CRC<input value={f.crc} onChange={set("crc")} placeholder="UF-000000/O-0" /></label>
          <label>Seu nome (responsável técnico)<input value={f.name} onChange={set("name")} required /></label>
          <label>E-mail<input type="email" value={f.email} onChange={set("email")} required /></label>
          <label>Senha<input type="password" autoComplete="new-password" value={f.password} onChange={set("password")} required /></label>
          <span className="muted">Mínimo de 10 caracteres com maiúscula, minúscula, número e símbolo.</span>
          <label style={{ flexDirection: "row", alignItems: "center" }}>
            <input type="checkbox" checked={f.accept_terms} onChange={set("accept_terms")} />
            Li e aceito os Termos de Uso, a Política de Privacidade (LGPD) e o Termo de Confidencialidade
          </label>
          <button disabled={busy || !f.accept_terms}>Cadastrar</button>
          <Link to="/login">Já tenho conta</Link>
        </form>
      )}
    </AuthCard>
  );
}

export function ForgotPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const { error, busy, run } = useSubmit();
  const submit = run(async () => setDone((await post<{ detail: string }>("/auth/password/forgot", { email })).detail));
  return (
    <AuthCard title="Recuperar senha">
      <Alert>{error}</Alert>
      <Alert kind="ok">{done}</Alert>
      <form className="form" onSubmit={submit}>
        <label>E-mail<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <button disabled={busy}>Enviar link</button>
        <Link to="/login">Voltar</Link>
      </form>
    </AuthCard>
  );
}

export function ResetPage() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const { error, busy, run, setError } = useSubmit();
  const submit = run(async () => {
    if (password !== confirm) return setError("As senhas não conferem");
    setDone((await post<{ detail: string }>("/auth/password/reset", { token: params.get("token"), new_password: password })).detail);
  });
  return (
    <AuthCard title="Definir nova senha">
      <Alert>{error}</Alert>
      {done ? (
        <>
          <Alert kind="ok">{done}</Alert>
          <Link to="/login">Ir para o login</Link>
        </>
      ) : (
        <form className="form" onSubmit={submit}>
          <label>Nova senha<input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <label>Confirmar senha<input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required /></label>
          <button disabled={busy}>Salvar</button>
        </form>
      )}
    </AuthCard>
  );
}
