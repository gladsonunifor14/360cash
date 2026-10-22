import { Fragment, useState } from "react";
import { api, ChartAccount, cnpjMask, dateBR, post } from "../api";
import { ClientPicker, useSession } from "../App";
import { Alert, Money, useLoad } from "../components/ui";

type Invoice = {
  id: string; direction: string; numero: string; serie: string; data_emissao: string; emit_nome: string;
  emit_cnpj: string; dest_nome: string; dest_documento: string; valor_total: string; cancelled: boolean;
};
type Item = { id: string; n_item: number; descricao: string; cfop: string; cfop_cliente: string; valor_total: string; operation: string; account_id: string | null; classification_source: string | null };
type ImportResult = { arquivo: string; status: string; detalhe: string | null };

export default function InvoicesPage() {
  const { clientId, user } = useSession();
  const [direction, setDirection] = useState("");
  const [results, setResults] = useState<ImportResult[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const list = useLoad<Invoice[]>(
    () => (clientId ? api(`/clients/${clientId}/invoices${direction ? `?direction=${direction}` : ""}`) : Promise.resolve([])),
    [clientId, direction],
  );

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    setError(null);
    try {
      setResults(await post<ImportResult[]>(`/clients/${clientId}/invoices/import`, fd));
      list.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <div className="topbar">
        <h1 className="grow" style={{ margin: 0 }}>Notas fiscais</h1>
        <ClientPicker />
        <select value={direction} onChange={(e) => setDirection(e.target.value)} aria-label="Tipo">
          <option value="">Emitidas e recebidas</option>
          <option value="emitida">Emitidas</option>
          <option value="recebida">Recebidas</option>
        </select>
      </div>
      <div className="card">
        <label>
          Importar XML de NF-e/NFC-e (arquivos .xml ou .zip; inclui eventos de cancelamento)
          <input type="file" multiple accept=".xml,.zip" onChange={(e) => upload(e.target.files)} disabled={!clientId} />
        </label>
        <Alert>{error}</Alert>
        {results.length > 0 && (
          <table style={{ marginTop: "1rem" }}>
            <tbody>{results.map((r, i) => (
              <tr key={i}><td>{r.arquivo}</td><td><span className="badge">{r.status}</span></td><td className="muted">{r.detalhe}</td></tr>
            ))}</tbody>
          </table>
        )}
      </div>
      <div className="card">
        <Alert>{list.error}</Alert>
        <table>
          <thead><tr><th>Emissão</th><th>Tipo</th><th>Número</th><th>Emitente</th><th>Destinatário</th><th className="num">Total</th><th /></tr></thead>
          <tbody>
            {list.data?.map((n) => (
              <Fragment key={n.id}>
                <tr style={n.cancelled ? { textDecoration: "line-through", opacity: .6 } : undefined}>
                  <td>{dateBR(n.data_emissao)}</td>
                  <td><span className="badge">{n.direction}</span></td>
                  <td>{n.numero}/{n.serie}</td>
                  <td>{n.emit_nome}<div className="muted">{cnpjMask(n.emit_cnpj ?? "")}</div></td>
                  <td>{n.dest_nome}<div className="muted">{cnpjMask(n.dest_documento ?? "")}</div></td>
                  <td className="num"><Money v={n.valor_total} /></td>
                  <td><button className="secondary" onClick={() => setOpen(open === n.id ? null : n.id)}>Itens</button></td>
                </tr>
                {open === n.id && <tr key={`${n.id}-i`}><td colSpan={7}><Items invoiceId={n.id} canEdit={user.role !== "cliente"} /></td></tr>}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Items({ invoiceId, canEdit }: { invoiceId: string; canEdit: boolean }) {
  const inv = useLoad<{ items: Item[] }>(() => api(`/invoices/${invoiceId}`), [invoiceId]);
  const accounts = useLoad<ChartAccount[]>(() => api("/chart-accounts"), []);
  const change = async (itemId: string, accountId: string) => {
    await api(`/invoice-items/${itemId}/classification`, { method: "PATCH", body: JSON.stringify({ account_id: accountId }) });
    inv.reload();
  };
  return (
    <table>
      <thead><tr><th>#</th><th>Descrição</th><th>CFOP XML</th><th>CFOP cliente</th><th>Operação</th><th>Conta gerencial</th><th className="num">Valor</th></tr></thead>
      <tbody>
        {inv.data?.items.map((it) => (
          <tr key={it.id}>
            <td>{it.n_item}</td><td>{it.descricao}</td><td>{it.cfop}</td><td>{it.cfop_cliente}</td><td>{it.operation}</td>
            <td>
              <select value={it.account_id ?? ""} disabled={!canEdit} onChange={(e) => change(it.id, e.target.value)}>
                <option value="">— sem efeito no resultado —</option>
                {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}
              </select>
              {it.classification_source && <span className="muted"> ({it.classification_source})</span>}
            </td>
            <td className="num"><Money v={it.valor_total} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
