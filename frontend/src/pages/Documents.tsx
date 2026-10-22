import { FormEvent, useState } from "react";
import { api, dateBR, post } from "../api";
import { useSession } from "../App";
import { Alert, useLoad } from "../components/ui";

type Doc = { id: string; category: string; filename: string; size_bytes: number; sha256: string; created_at: string };
const CATEGORIES = ["contrato", "procuracao", "nfe_xml", "extrato", "societario", "fiscal", "trabalhista", "outros"];

export default function DocumentsPage() {
  const { clientId } = useSession();
  const [category, setCategory] = useState("outros");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const docs = useLoad<Doc[]>(() => (clientId ? api(`/documents?client_id=${clientId}`) : Promise.resolve([])), [clientId]);

  const upload = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("category", category);
    fd.append("client_id", clientId);
    try {
      await post("/documents", fd);
      setFile(null);
      docs.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const download = async (d: Doc) => {
    const blob = await api<Blob>(`/documents/${d.id}/download`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = d.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="topbar"><h1 tabIndex={-1} className="grow">Repositório de documentos</h1></div>
      <div className="card">
        <Alert>{error}</Alert>
        <form className="row" onSubmit={upload}>
          <label>Categoria
            <select value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select>
          </label>
          <label>Arquivo (PDF, imagem, XML, CSV, OFX, planilha; até 15 MB)<input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          <button disabled={!file || !clientId}>Enviar</button>
        </form>
      </div>
      <div className="card">
        <table>
          <thead><tr><th>Arquivo</th><th>Categoria</th><th className="num">Tamanho</th><th>Enviado em</th><th>SHA-256</th><th /></tr></thead>
          <tbody>
            {docs.data?.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td><td><span className="badge">{d.category}</span></td>
                <td className="num">{(d.size_bytes / 1024).toFixed(1)} KB</td><td>{dateBR(d.created_at)}</td>
                <td className="muted">{d.sha256.slice(0, 16)}…</td>
                <td><button className="secondary" onClick={() => download(d)}>Baixar</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
