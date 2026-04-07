"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/store/app";
import {
  api, getPessoas, getEmpresas, gerarFichaPessoa, gerarFichaEmpresa,
  osintConsultaAvulsa, osintSugestao, osintLote,
} from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import {
  UserSearch, Bot, Target, AlertTriangle, Building, User, Search,
  FileSearch, CheckCircle, XCircle, Phone, Mail, MapPin, Car,
  Shield, Briefcase, ChevronDown, ChevronRight, Loader2, Play,
  TriangleAlert, MinusCircle, Wallet, Coins, ArrowRightLeft,
  History, Info, ExternalLink,
} from "lucide-react";

// ── Tipos ─────────────────────────────────────────────────────────────────────

type Staleness = "fresco" | "desatualizado" | "ausente";
type PerfilOpt = null | 1 | 2 | 3 | 4;

interface DadoCampo {
  presente: boolean;
  staleness: Staleness;
  data_doc?: string | null;
  data_doc_fmt?: string | null;
  texto?: string | null;
}

interface HistoricoInquerito {
  inquerito_id: string;
  numero: string;
  ano?: number | null;
  descricao?: string;
  tipo_pessoa: string;
  created_at: string;
}

interface PersonagemAnalise {
  pessoa_id: string;
  nome: string;
  tipo_pessoa: string;
  cpf?: string | null;
  dados_nos_autos: { cpf: DadoCampo; telefone: DadoCampo; endereco: DadoCampo };
  historico_inqueritos: HistoricoInquerito[];
  perfil_sugerido: number;
  perfil_sugerido_label: string;
  custo_estimado: number;
  justificativa: string;
  chunks_encontrados: number;
}

// ── Constantes ────────────────────────────────────────────────────────────────

const OSINT_MODULOS = [
  { id: "cadastro_pf_plus", label: "Cadastro Plus (Foco Ctt/Wpp)", custo: 2.50, color: "text-green-400" },
  { id: "vinculo_empregaticio", label: "Vínculo CLT / RH", custo: 3.10, color: "text-green-400" },
  { id: "historico_veiculos_pf", label: "Histórico Veicular", custo: 0.90, color: "text-lime-400" },
  { id: "bpc", label: "Benefícios BPC", custo: 1.50, color: "text-blue-400" },
  { id: "mandados_prisao", label: "Mandados de Prisão", custo: 1.20, color: "text-red-400" },
  { id: "pep", label: "Pessoa Exposta (PEP)", custo: 0.72, color: "text-yellow-400" },
  { id: "aml", label: "AML / Lavagem + PEP + Sócios", custo: 0.72, color: "text-orange-400" },
  { id: "ceis", label: "CEIS (Inidôneas)", custo: 0.36, color: "text-orange-400" },
  { id: "cnep", label: "CNEP (Punidas)", custo: 0.36, color: "text-orange-400" },
  { id: "processos_tj", label: "Processos TJ (Civil/Crim)", custo: 2.00, color: "text-red-400" },
  { id: "ofac", label: "Lista OFAC", custo: 0.36, color: "text-red-400" },
  { id: "lista_onu", label: "Lista ONU", custo: 0.36, color: "text-red-400" },
];

const initSugestao = (perfil: number): string[] => {
  if (perfil === 1) return ["cadastro_pf_plus", "historico_veiculos_pf"];
  if (perfil === 2) return ["cadastro_pf_plus", "historico_veiculos_pf", "mandados_prisao", "pep"];
  if (perfil === 3) return ["cadastro_pf_plus", "historico_veiculos_pf", "mandados_prisao", "aml", "ceis"];
  if (perfil === 4) return ["cadastro_pf_plus", "vinculo_empregaticio", "historico_veiculos_pf", "mandados_prisao", "aml", "processos_tj"];
  return [];
};

// ── Componente de Investigação Cripto (Novo!) ────────────────────────────────

function InvestigacaoCripto() {
  const [address, setAddress] = useState("");
  const [analisando, setAnalisando] = useState(false);
  const [resultado, setResultado] = useState<any | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const handleAnalisar = async () => {
    if (!address.trim()) return;
    setAnalisando(true); setErro(null); setResultado(null);
    try {
      // Simulação de chamada ao Agente Cripto via API
      // Nota: O Agente Cripto é acionado pelo Copiloto, mas aqui fornecemos uma UI direta.
      const res = await api.post("/agentes/cripto/analisar", { address: address.trim() });
      setResultado(res.data);
    } catch (e: any) {
      setErro(e?.response?.data?.detail || "Erro ao analisar carteira. Verifique se as chaves de API estão configuradas.");
    } finally { setAnalisando(false); }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-700">
      <Card className="bg-zinc-900/50 border-zinc-800 border-dashed">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Wallet className="text-orange-500" size={20} /> Investigação de Ativos Blockchain
          </CardTitle>
          <CardDescription>
            Rastreie o fluxo de capitais e verifique reportes criminais (Chainabuse + Etherscan).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3">
            <div className="relative flex-1">
              <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none text-zinc-500">
                <Coins size={16} />
              </div>
              <Input 
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Endereço da Carteira (ex: 0x...)" 
                className="pl-10 bg-zinc-950 border-zinc-700 text-zinc-100 h-11"
              />
            </div>
            <Button 
              onClick={handleAnalisar} 
              disabled={analisando || !address}
              className="bg-orange-600 hover:bg-orange-700 text-white h-11 px-6 shadow-lg shadow-orange-900/10"
            >
              {analisando ? <Loader2 className="animate-spin mr-2" size={18} /> : <Search className="mr-2" size={18} />}
              Analisar
            </Button>
          </div>
        </CardContent>
      </Card>

      {erro && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex gap-3">
          <TriangleAlert size={18} className="shrink-0" /> {erro}
        </div>
      )}

      {resultado && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-in slide-in-from-bottom-4 duration-500">
          {/* Status Chainabuse */}
          <Card className="bg-zinc-900 border-zinc-800 h-full">
            <CardHeader className="pb-3 border-b border-zinc-800">
              <div className="flex justify-between items-center">
                <CardTitle className="text-sm font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                  <Shield size={14} className="text-blue-400" /> Vínculo Criminal (Chainabuse)
                </CardTitle>
                <Badge variant={resultado.chainabuse?.status === "denunciado" ? "destructive" : "outline"} className="capitalize">
                  {resultado.chainabuse?.status || "Desconhecido"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-3">
              {resultado.chainabuse?.total_reportes > 0 ? (
                <div className="space-y-4">
                  <div className="p-3 bg-red-500/5 border border-red-500/20 rounded text-red-500 text-xs">
                    Detectados {resultado.chainabuse.total_reportes} reportes criminais para este endereço.
                  </div>
                  <ScrollArea className="h-48">
                    <div className="space-y-2">
                      {resultado.chainabuse.detalhes?.map((rep: any, i: number) => (
                        <div key={i} className="text-[11px] p-2 bg-zinc-950 border border-zinc-800 rounded">
                          <p className="text-zinc-300 font-medium">{rep.category || "Reporte"}</p>
                          <p className="text-zinc-500 mt-1">{rep.description}</p>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center text-zinc-500">
                  <CheckCircle className="text-green-500 mb-3" size={32} />
                  <p className="text-sm font-medium text-zinc-300">Nenhum reporte encontrado</p>
                  <p className="text-xs px-6 mt-1">Este endereço não figura em bases de denúncias públicas.</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Fluxo de Ativos */}
          <Card className="bg-zinc-900 border-zinc-800 h-full">
            <CardHeader className="pb-3 border-b border-zinc-800">
              <CardTitle className="text-sm font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                <ArrowRightLeft size={14} className="text-orange-400" /> Transações Recentes (Fluxo)
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-[300px]">
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800 hover:bg-transparent">
                      <TableHead className="text-[10px] text-zinc-500">Data</TableHead>
                      <TableHead className="text-[10px] text-zinc-500 text-right">Valor (ETH)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resultado.fluxo?.transacoes?.map((tx: any, i: number) => (
                      <TableRow key={i} className="border-zinc-800">
                        <TableCell className="text-[10px] text-zinc-400">
                          {new Date(tx.timeStamp * 1000).toLocaleDateString()}
                        </TableCell>
                        <TableCell className="text-right text-[11px] font-mono text-zinc-200">
                          {(tx.value / 1e18).toFixed(4)}
                        </TableCell>
                      </TableRow>
                    ))}
                    {!resultado.fluxo?.transacoes?.length && (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center py-12 text-zinc-500 text-xs">Sem transações recentes para exibir.</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </ScrollArea>
              <div className="p-3 border-t border-zinc-800 bg-zinc-950/50">
                <Button variant="ghost" className="w-full text-[10px] text-zinc-500 h-6 hover:text-zinc-300">
                  <History size={11} className="mr-1" /> Ver histórico completo no Explorer <ExternalLink size={10} className="ml-1" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function stalenessIcon(s: Staleness, fmt?: string | null) {
  if (s === "fresco")       return <span className="text-green-400 text-[10px]" title={fmt || ""}>✓</span>;
  if (s === "desatualizado") return <span className="text-yellow-400 text-[10px]" title={fmt || ""}>⚠</span>;
  return <span className="text-zinc-600 text-[10px]">—</span>;
}

function DadosBadge({ campo, label }: { campo: DadoCampo; label: string }) {
  const cor = campo.staleness === "fresco" ? "border-green-700/40 text-green-400 bg-green-500/5"
    : campo.staleness === "desatualizado" ? "border-yellow-700/40 text-yellow-400 bg-yellow-500/5"
    : "border-zinc-700 text-zinc-600";
  const title = campo.data_doc_fmt ? `${label}: ${campo.data_doc_fmt}` : label;
  return (
    <span title={campo.texto ? `${title} — "${campo.texto}"` : title}
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] border cursor-default ${cor}`}>
      {label} {stalenessIcon(campo.staleness, campo.data_doc_fmt)}
    </span>
  );
}

// ── Componentes de resultado avulso (mantidos) ────────────────────────────────

function SecaoResultado({ titulo, icone: Icone, children }: { titulo: string; icone: any; children: React.ReactNode }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-2 mb-3">
        <Icone size={13} /> {titulo}
      </h4>
      {children}
    </div>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className={`flex items-center gap-1.5 text-xs ${ok ? "text-green-400" : "text-red-400"}`}>
      {ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
      {label}
    </div>
  );
}

function ResultadoAvulso({ dados }: { dados: any }) {
  const cadastro = dados.cadastro;
  const aml = dados.aml;
  const mandados = dados.mandados_prisao;
  const veiculos = dados.historico_veiculos;
  const veiculo = dados.veiculo;
  const receita = dados.receita_federal;
  const mandadosNome = dados.mandados_por_nome;

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex flex-wrap gap-1.5">
        {dados.fontes_consultadas?.map((f: string) => (
          <Badge key={f} variant="outline" className="text-xs border-green-700/40 text-green-400 bg-green-500/5">{f}</Badge>
        ))}
        {dados.fontes_sem_dados?.map((f: any) => (
          <Badge key={f.fonte} variant="outline" className="text-xs border-red-700/40 text-red-400 bg-red-500/5">{f.fonte}</Badge>
        ))}
      </div>
      
      {dados.historico_inqueritos && dados.historico_inqueritos.length > 0 && (
        <div className="bg-orange-500/10 border border-orange-500/20 rounded-lg p-4 flex gap-3 text-orange-400">
          <AlertTriangle size={18} className="shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold mb-1">ALERTA DE CRUZAMENTO</p>
            <p className="mb-2">Este alvo já figura em outros Inquéritos sob sua custódia:</p>
            <ul className="list-disc ml-4 space-y-1 text-xs">
              {dados.historico_inqueritos.map((h: any, i: number) => (
                <li key={i}>
                  IP {h.numero} <span className="text-orange-500/70">({h.tipo_pessoa || h.tipo_empresa})</span> — {h.descricao}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {cadastro && (
        <SecaoResultado titulo="Qualificação" icone={User}>
          <div className="space-y-1 text-sm text-zinc-200">
            <p className="text-base font-semibold text-zinc-100">{cadastro.nome}</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400 mt-2">
              {cadastro.dataNascimento && <span>Nasc.: {cadastro.dataNascimento.split(" ")[0]}</span>}
              {cadastro.nomeMae && <span>Mãe: {cadastro.nomeMae}</span>}
              {cadastro.situacaoCadastral && <span>Situação: <span className="text-zinc-200">{cadastro.situacaoCadastral}</span></span>}
              {cadastro.classeSocial && <span>Classe: {cadastro.classeSocial}</span>}
              {cadastro.rendaEstimada && <span>Renda est.: R$ {parseFloat(cadastro.rendaEstimada).toLocaleString("pt-BR", {minimumFractionDigits: 2})}</span>}
              {cadastro.cbo && <span className="col-span-2">Ocupação: {cadastro.cbo}</span>}
            </div>
          </div>
        </SecaoResultado>
      )}
      {(mandados || aml) && (
        <SecaoResultado titulo="Alertas" icone={Shield}>
          <div className="grid grid-cols-2 gap-2">
            {mandados && <StatusBadge ok={!mandados.possuiMandado} label={mandados.possuiMandado ? "MANDADO ATIVO" : "Sem mandados"} />}
            {aml && <StatusBadge ok={!aml.pep} label={aml.pep ? "É PEP" : "Não é PEP"} />}
            {aml && <StatusBadge ok={!aml.obito} label={aml.obito ? "ÓBITO REGISTRADO" : "Sem óbito"} />}
            {dados.ceis === null && <StatusBadge ok={true} label="Sem restrição CEIS" />}
            {dados.cnep === null && <StatusBadge ok={true} label="Sem restrição CNEP" />}
          </div>
        </SecaoResultado>
      )}
      {cadastro?.telefones?.length > 0 && (
        <SecaoResultado titulo="Contatos" icone={Phone}>
          <div className="space-y-1">
            {cadastro.telefones.slice(0, 5).map((t: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-zinc-200 font-mono">{t.telefoneComDDD}</span>
                <div className="flex gap-1">
                  <Badge variant="outline" className="text-zinc-500 border-zinc-700 text-[10px]">{t.tipoTelefone}</Badge>
                  {t.whatsApp && <Badge variant="outline" className="border-green-700/40 text-green-400 text-[10px]">WhatsApp</Badge>}
                </div>
              </div>
            ))}
            {cadastro.emails?.slice(0, 3).map((e: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs text-zinc-400">
                <Mail size={11} /> {e.enderecoEmail}
              </div>
            ))}
          </div>
        </SecaoResultado>
      )}
      {cadastro?.enderecos?.length > 0 && (
        <SecaoResultado titulo="Endereços" icone={MapPin}>
          <div className="space-y-1">
            {cadastro.enderecos.map((e: any, i: number) => (
              <div key={i} className="text-xs text-zinc-300">
                {e.logradouro}, {e.numero}{e.complemento ? ` ${e.complemento}` : ""} — {e.bairro}, {e.cidade}/{e.uf}
              </div>
            ))}
          </div>
        </SecaoResultado>
      )}
      {aml?.sociedades?.length > 0 && (
        <SecaoResultado titulo="Vínculos Empresariais" icone={Briefcase}>
          <div className="space-y-2">
            {aml.sociedades.map((s: any, i: number) => (
              <div key={i} className="bg-zinc-800/50 rounded p-2">
                <p className="text-xs font-medium text-zinc-200">{s.razaoSocial}</p>
                <div className="flex gap-2 mt-1 flex-wrap">
                  <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-400">{s.cnpj}</Badge>
                  {!s.baixada && <Badge variant="outline" className="text-[10px] border-green-700/40 text-green-400">Ativa</Badge>}
                </div>
              </div>
            ))}
          </div>
        </SecaoResultado>
      )}
      {veiculos && (
        <SecaoResultado titulo="Veículos" icone={Car}>
          {veiculos.veiculos?.length > 0 ? (
            <div className="space-y-1">
              {veiculos.veiculos.map((v: any, i: number) => (
                <div key={i} className="text-xs text-zinc-300">{v.placa} — {v.marca} {v.modelo} ({v.anoFabricacao})</div>
              ))}
            </div>
          ) : <p className="text-xs text-zinc-500">Nenhum veículo registrado</p>}
        </SecaoResultado>
      )}
      {veiculo && (
        <SecaoResultado titulo="Veículo Consultado" icone={Car}>
          <div className="text-xs space-y-1 text-zinc-300">
            {veiculo.placa && <p><span className="text-zinc-500">Placa:</span> {veiculo.placa}</p>}
            {veiculo.marca && <p><span className="text-zinc-500">Veículo:</span> {veiculo.marca} {veiculo.modelo} {veiculo.anoFabricacao}</p>}
            {veiculo.proprietario && <p><span className="text-zinc-500">Proprietário:</span> {veiculo.proprietario}</p>}
          </div>
        </SecaoResultado>
      )}
      {receita && (
        <SecaoResultado titulo="Receita Federal" icone={Building}>
          <div className="text-xs space-y-1 text-zinc-300">
            <p className="font-medium text-zinc-100">{receita.razaoSocial || receita.nomeFantasia}</p>
            {receita.situacaoCadastral && <p><span className="text-zinc-500">Situação:</span> {receita.situacaoCadastral}</p>}
          </div>
        </SecaoResultado>
      )}
      {mandadosNome && (
        <SecaoResultado titulo="Mandados por Nome" icone={Shield}>
          <StatusBadge ok={!mandadosNome.possuiMandado} label={mandadosNome.possuiMandado ? `${mandadosNome.mandadosPrisao?.length} mandado(s) ativo(s)` : "Sem mandados por este nome"} />
        </SecaoResultado>
      )}
      {dados.fontes_consultadas?.length === 0 && (
        <p className="text-sm text-zinc-500 text-center py-4">Nenhuma fonte retornou dados.</p>
      )}
    </div>
  );
}

// ── Consulta Avulsa Dialog ────────────────────────────────────────────────────

function ConsultaAvulsaDialog() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ cpf: "", cnpj: "", placa: "", nome: "", data_nascimento: "", rg: "", uf: "RJ" });
  const [consultando, setConsultando] = useState(false);
  const [resultado, setResultado] = useState<any | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  const handleConsultar = async () => {
    if (!Object.entries(form).some(([k, v]) => k !== "uf" && v.trim())) return;
    setConsultando(true); setErro(null); setResultado(null);
    try {
      const res = await osintConsultaAvulsa(form);
      setResultado(res.dados);
    } catch (e: any) {
      setErro(e?.response?.data?.detail || "Erro na consulta.");
    } finally { setConsultando(false); }
  };

  const limpar = () => { setForm({ cpf: "", cnpj: "", placa: "", nome: "", data_nascimento: "", rg: "", uf: "RJ" }); setResultado(null); setErro(null); };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={
        <Button variant="outline" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 gap-2">
          <FileSearch size={15} /> Consulta Avulsa
        </Button>
      } />
      <DialogContent className="bg-zinc-950 border-zinc-800 max-w-4xl w-full max-h-[90vh] flex flex-col" showCloseButton>
        <DialogHeader>
          <DialogTitle className="text-zinc-100 flex items-center gap-2">
            <FileSearch size={18} className="text-blue-400" /> Consulta OSINT Avulsa
          </DialogTitle>
          <p className="text-xs text-zinc-500">Preencha ao menos um campo.</p>
        </DialogHeader>
        <div className="flex gap-6 flex-1 min-h-0 overflow-hidden mt-2">
          <div className="w-72 shrink-0 space-y-3">
            {[
              { k: "cpf", label: "CPF", ph: "000.000.000-00" },
              { k: "cnpj", label: "CNPJ", ph: "00.000.000/0001-00" },
              { k: "placa", label: "Placa", ph: "ABC1D23" },
            ].map(({ k, label, ph }) => (
              <div key={k}>
                <label className="text-xs text-zinc-400 mb-1 block">{label}</label>
                <Input value={(form as any)[k]} onChange={e => set(k, k === "placa" ? e.target.value.toUpperCase() : e.target.value)}
                  placeholder={ph} className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
              </div>
            ))}
            <div className="border-t border-zinc-800 pt-3 space-y-2">
              <p className="text-xs text-zinc-600">Sem CPF — busca por identificação parcial:</p>
              {[
                { k: "nome", label: "Nome", ph: "Nome completo" },
                { k: "rg", label: "RG", ph: "0000000" },
                { k: "data_nascimento", label: "Data Nascimento", ph: "DD/MM/AAAA" },
              ].map(({ k, label, ph }) => (
                <div key={k}>
                  <label className="text-xs text-zinc-400 mb-1 block">{label}</label>
                  <Input value={(form as any)[k]} onChange={e => set(k, e.target.value)}
                    placeholder={ph} className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
                </div>
              ))}
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">UF</label>
                <Input value={form.uf} onChange={e => set("uf", e.target.value.toUpperCase())}
                  placeholder="RJ" maxLength={2} className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8 w-20" />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleConsultar} disabled={consultando} className="flex-1 bg-blue-600 hover:bg-blue-700 h-9 text-sm gap-2">
                {consultando ? <><Loader2 size={14} className="animate-spin" /> Consultando...</> : <><Search size={14} /> Consultar</>}
              </Button>
              {resultado && <Button onClick={limpar} variant="outline" className="border-zinc-700 text-zinc-400 hover:bg-zinc-800 h-9 text-sm px-3">Limpar</Button>}
            </div>
          </div>
          <div className="flex-1 min-w-0 border-l border-zinc-800 pl-6 overflow-hidden">
            <ScrollArea className="h-full max-h-[65vh]">
              {!resultado && !erro && !consultando && (
                <div className="flex flex-col items-center justify-center h-48 text-zinc-600 text-center text-sm">
                  <Search className="w-10 h-10 mb-3 text-zinc-800" />
                  <p>Preencha os campos e clique em Consultar.</p>
                </div>
              )}
              {consultando && <div className="flex items-center gap-3 text-zinc-400 text-sm py-8 justify-center"><Loader2 size={18} className="animate-spin text-blue-500" /> Acessando bases de dados...</div>}
              {erro && <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex gap-3 text-red-400 text-sm"><AlertTriangle size={16} className="shrink-0 mt-0.5" /> {erro}</div>}
              {resultado && <ResultadoAvulso dados={resultado} />}
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Painel de Personagens ─────────────────────────────────────────────────────

function PainelPersonagens({ inqueritoId }: { inqueritoId: string }) {
  const [analise, setAnalise] = useState<any | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erroAnalise, setErroAnalise] = useState<string | null>(null);

  // Módulos selecionados por pessoa: pessoa_id → string[]
  const [modulos, setModulos] = useState<Record<string, string[]>>({});
  // Justificativa expandida por pessoa
  const [expandidos, setExpandidos] = useState<Record<string, boolean>>({});

  // Estado de execução do lote
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [executando, setExecutando] = useState(false);
  const [resultados, setResultados] = useState<Record<string, any>>({});
  const [erroExec, setErroExec] = useState<string | null>(null);

  useEffect(() => {
    setAnalise(null); setErroAnalise(null); setResultados({}); setModulos({});
    setCarregando(true);
    osintSugestao(inqueritoId)
      .then(res => {
        const a = res.analise;
        setAnalise(a);
        // Inicializar modulos com base na sugestão Copiloto
        const init: Record<string, string[]> = {};
        (a.personagens || []).forEach((p: PersonagemAnalise) => {
          init[p.pessoa_id] = initSugestao(p.perfil_sugerido);
        });
        setModulos(init);
      })
      .catch(e => setErroAnalise(e?.response?.data?.detail || "Erro ao analisar personagens."))
      .finally(() => setCarregando(false));
  }, [inqueritoId]);

  const personagens: PersonagemAnalise[] = analise?.personagens || [];
  const custoTotal = personagens.reduce((acc, p) => {
    const mods = modulos[p.pessoa_id] || [];
    const custo_local = mods.reduce((sum, m) => sum + (OSINT_MODULOS.find(x => x.id === m)?.custo || 0), 0);
    return acc + custo_local;
  }, 0);

  const toggleExpand = (id: string) => setExpandidos(e => ({ ...e, [id]: !e[id] }));

  const toggleModulo = (pessoaId: string, moduloId: string) => {
    setModulos(prev => {
      const atuais = prev[pessoaId] || [];
      if (atuais.includes(moduloId)) {
        return { ...prev, [pessoaId]: atuais.filter(m => m !== moduloId) };
      }
      return { ...prev, [pessoaId]: [...atuais, moduloId] };
    });
  };

  const itensAtivos = personagens.filter(p => (modulos[p.pessoa_id] || []).length > 0);

  const handleExecutar = async () => {
    setConfirmOpen(false);
    setExecutando(true); setErroExec(null);
    try {
      const itens = personagens.map(p => ({ pessoa_id: p.pessoa_id, modulos: modulos[p.pessoa_id] || [] }));
      const res = await osintLote(inqueritoId, itens);
      const mapa: Record<string, any> = {};
      (res.resultados || []).forEach((r: any) => { mapa[r.pessoa_id] = r; });
      setResultados(mapa);
    } catch (e: any) {
      setErroExec(e?.response?.data?.detail || "Erro ao executar lote.");
    } finally { setExecutando(false); }
  };

  if (carregando) return (
    <div className="flex items-center justify-center h-64 gap-3 text-zinc-400">
      <Loader2 size={22} className="animate-spin text-blue-500" />
      Analisando personagens nos autos...
    </div>
  );

  if (erroAnalise) return (
    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex gap-3 text-red-400 text-sm">
      <AlertTriangle size={16} className="shrink-0 mt-1" /> {erroAnalise}
    </div>
  );

  if (!personagens.length) return (
    <div className="flex flex-col items-center justify-center h-64 text-zinc-500 text-center">
      <User className="w-12 h-12 mb-3 text-zinc-800" />
      <p className="text-sm">Nenhum personagem indexado neste inquérito.</p>
      <p className="text-xs mt-1 text-zinc-600">Inicie a ingestão de documentos para detectar pessoas automaticamente.</p>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      {/* Crime complexo badge */}
      {analise && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-zinc-500">Classificação do crime:</span>
          {analise.crime_complexo
            ? <Badge variant="outline" className="border-red-700/40 text-red-400 bg-red-500/5">Complexo — lavagem / tráfico / corrupção</Badge>
            : <Badge variant="outline" className="border-zinc-700 text-zinc-400">Crime simples</Badge>}
          <span className="text-zinc-600">· {personagens.length} personagens</span>
        </div>
      )}

      {/* Tabela */}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 bg-zinc-900/60 hover:bg-zinc-900/60">
              <TableHead className="text-zinc-400 text-xs w-52">Personagem</TableHead>
              <TableHead className="text-zinc-400 text-xs w-28">Papel</TableHead>
              <TableHead className="text-zinc-400 text-xs">Dados nos autos</TableHead>
              <TableHead className="text-zinc-400 text-xs w-36">Histórico</TableHead>
              <TableHead className="text-zinc-400 text-xs w-52">Perfil OSINT</TableHead>
              <TableHead className="text-zinc-400 text-xs text-right w-24">Custo</TableHead>
              <TableHead className="text-zinc-400 text-xs w-20 text-center">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {personagens.map((p) => {
              const mods = modulos[p.pessoa_id] || [];
              const custo = mods.reduce((sum, m) => sum + (OSINT_MODULOS.find(x => x.id === m)?.custo || 0), 0);
              const resultado = resultados[p.pessoa_id];
              const expandido = expandidos[p.pessoa_id];

              return (
                <>
                  <TableRow key={p.pessoa_id} className="border-zinc-800 hover:bg-zinc-900/40">
                    {/* Nome */}
                    <TableCell>
                      <button
                        onClick={() => toggleExpand(p.pessoa_id)}
                        className="flex items-start gap-1.5 text-left group"
                      >
                        {expandido
                          ? <ChevronDown size={13} className="text-zinc-500 mt-0.5 shrink-0" />
                          : <ChevronRight size={13} className="text-zinc-500 mt-0.5 shrink-0" />}
                        <div>
                          <p className="text-sm text-zinc-200 group-hover:text-zinc-100 font-medium leading-tight">{p.nome}</p>
                          {p.cpf && <p className="text-[10px] text-zinc-600 mt-0.5">CPF {p.cpf}</p>}
                        </div>
                      </button>
                    </TableCell>

                    {/* Papel */}
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-400 capitalize">
                        {p.tipo_pessoa}
                      </Badge>
                    </TableCell>

                    {/* Dados nos autos */}
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        <DadosBadge campo={p.dados_nos_autos.cpf}      label="CPF" />
                        <DadosBadge campo={p.dados_nos_autos.telefone}  label="Tel" />
                        <DadosBadge campo={p.dados_nos_autos.endereco}  label="End" />
                      </div>
                    </TableCell>

                    {/* Histórico cruzado */}
                    <TableCell>
                      {p.historico_inqueritos?.length > 0 ? (
                        <span
                          title={p.historico_inqueritos.map((h: any) => `${h.numero} (${h.tipo_pessoa})`).join("\n")}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border border-orange-700/40 text-orange-400 bg-orange-500/5 cursor-default"
                        >
                          ⚠ {p.historico_inqueritos.length} inq.
                        </span>
                      ) : (
                        <span className="text-[10px] text-zinc-700">—</span>
                      )}
                    </TableCell>

                    {/* Módulos checkboxes inline */}
                    <TableCell>
                      <div className="flex flex-col gap-1 max-h-24 overflow-y-auto">
                        {OSINT_MODULOS.map(mod => {
                          const isChecked = (modulos[p.pessoa_id] || []).includes(mod.id);
                          return (
                            <label key={mod.id} className="flex items-center gap-2 cursor-pointer group">
                              <input 
                                type="checkbox" 
                                checked={isChecked}
                                onChange={() => toggleModulo(p.pessoa_id, mod.id)}
                                className="w-3 h-3 cursor-pointer accent-blue-500 bg-zinc-900 border-zinc-700 rounded-sm"
                              />
                              <span className={`text-[10px] truncate w-36 ${isChecked ? mod.color : 'text-zinc-500'} group-hover:text-zinc-300`}>
                                {mod.label}
                              </span>
                            </label>
                          )
                        })}
                      </div>
                    </TableCell>

                    {/* Custo */}
                    <TableCell className="text-right">
                      {custo > 0
                        ? <span className="text-xs text-zinc-300 font-mono">R$ {custo.toFixed(2)}</span>
                        : <span className="text-xs text-zinc-600">—</span>}
                    </TableCell>

                    {/* Status resultado */}
                    <TableCell className="text-center">
                      {resultado ? (
                        resultado.status === "concluido" ? <CheckCircle size={14} className="text-green-400 mx-auto" />
                        : resultado.status === "ignorado" ? <MinusCircle size={14} className="text-zinc-600 mx-auto" />
                        : <span title={resultado.mensagem}><XCircle size={14} className="text-red-400 mx-auto" /></span>
                      ) : executando ? <Loader2 size={14} className="animate-spin text-blue-400 mx-auto" />
                        : null}
                    </TableCell>
                  </TableRow>

                  {/* Justificativa expandida */}
                  {expandido && (
                    <TableRow key={`${p.pessoa_id}-expand`} className="border-zinc-800 bg-zinc-900/20 hover:bg-zinc-900/20">
                      <TableCell colSpan={7} className="py-3 px-4">
                        <div className="ml-5 space-y-2">
                          <p className="text-xs text-zinc-400 italic leading-relaxed">
                            "{p.justificativa}"
                          </p>
                          {p.historico_inqueritos?.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 text-[10px]">
                              <span className="text-orange-400 font-medium">Histórico:</span>
                              {p.historico_inqueritos.map((h: any, i: number) => (
                                <span key={i} className="px-1.5 py-0.5 rounded border border-orange-700/30 text-orange-300 bg-orange-500/5">
                                  {h.numero} · {h.tipo_pessoa}
                                </span>
                              ))}
                            </div>
                          )}
                          {resultado?.status === "concluido" && resultado?.dados && (
                            <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                              <span className="text-zinc-500">APIs executadas:</span>
                              {resultado.dados.apis_executadas?.map((a: string) => (
                                <Badge key={a} variant="outline" className="text-[10px] border-green-700/30 text-green-400">{a}</Badge>
                              ))}
                              {resultado.dados.cadastro?.telefones?.map((t: any, i: number) => (
                                <span key={i} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] ${t.whatsApp ? "border-green-700/40 text-green-300 bg-green-500/5" : "border-zinc-700 text-zinc-500"}`}>
                                  {t.telefoneComDDD} {t.whatsApp ? "· WhatsApp ✓" : ""}
                                </span>
                              ))}
                            </div>
                          )}
                          {resultado?.status === "erro" && (
                            <p className="text-xs text-red-400">Erro: {resultado.mensagem}</p>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Rodapé */}
      <div className="flex items-center justify-between border-t border-zinc-800 pt-3">
        <div className="text-sm text-zinc-400">
          {itensAtivos.length > 0
            ? <>{itensAtivos.length} personagem(ns) · custo estimado: <span className="text-zinc-100 font-mono font-medium">R$ {custoTotal.toFixed(2)}</span></>
            : <span className="text-zinc-600">Todos marcados como Ignorar</span>}
        </div>
        <div className="flex items-center gap-3">
          {erroExec && <p className="text-xs text-red-400">{erroExec}</p>}
          {Object.keys(resultados).length > 0 && (
            <Button variant="outline" onClick={() => setResultados({})}
              className="border-zinc-700 text-zinc-400 hover:bg-zinc-800 text-xs h-8 px-3">
              Limpar resultados
            </Button>
          )}
          <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <DialogTrigger render={
              <Button disabled={itensAtivos.length === 0 || executando}
                className="bg-blue-600 hover:bg-blue-700 gap-2 h-9">
                {executando ? <><Loader2 size={14} className="animate-spin" /> Executando...</>
                  : <><Play size={14} /> Executar seleção</>}
              </Button>
            } />
            <DialogContent className="bg-zinc-950 border-zinc-800 max-w-md" showCloseButton>
              <DialogHeader>
                <DialogTitle className="text-zinc-100">Confirmar execução OSINT</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 mt-2">
                <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-2">
                  {itensAtivos.map(p => {
                    const mods = modulos[p.pessoa_id] || [];
                    return (
                      <div key={p.pessoa_id} className="flex flex-col text-sm border-b border-zinc-800 pb-2">
                        <span className="text-zinc-300 font-medium">{p.nome}</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {mods.map(mID => {
                            const mm = OSINT_MODULOS.find(x => x.id === mID);
                            return mm ? <span key={mID} className={`text-[10px] px-1.5 py-0.5 bg-zinc-950 border border-zinc-800 rounded ${mm.color}`}>{mm.label}</span> : null;
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="flex items-center justify-between text-sm border-t border-zinc-800 pt-3">
                  <span className="text-zinc-400">Custo estimado total</span>
                  <span className="text-zinc-100 font-mono font-semibold">R$ {custoTotal.toFixed(2)}</span>
                </div>
                <p className="text-xs text-zinc-500">Esta operação consumirá créditos da conta direct.data. Os dados ficam em cache por 24h.</p>
                <div className="flex gap-3">
                  <Button onClick={() => setConfirmOpen(false)} variant="outline"
                    className="flex-1 border-zinc-700 text-zinc-400 hover:bg-zinc-800">
                    Cancelar
                  </Button>
                  <Button onClick={handleExecutar} className="flex-1 bg-blue-600 hover:bg-blue-700">
                    Confirmar e executar
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </div>
  );
}

// ── Ficha Individual ──────────────────────────────────────────────────────────

function FichaIndividual({ inqueritoId }: { inqueritoId: string }) {
  const [pessoas, setPessoas] = useState<any[]>([]);
  const [empresas, setEmpresas] = useState<any[]>([]);
  const [loadingEntidades, setLoadingEntidades] = useState(false);
  const [alvoSelecionado, setAlvoSelecionado] = useState<{id: string, tipo: "pessoa" | "empresa"} | null>(null);
  const [gerando, setGerando] = useState(false);
  const [fichaRenderizada, setFichaRenderizada] = useState<any | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setLoadingEntidades(true);
    Promise.all([
      getPessoas(inqueritoId).catch(() => []),
      getEmpresas(inqueritoId).catch(() => [])
    ]).then(([p, e]) => { setPessoas(p); setEmpresas(e); }).finally(() => setLoadingEntidades(false));
  }, [inqueritoId]);

  const handleGerarFicha = async () => {
    if (!alvoSelecionado) return;
    setGerando(true); setErro(null); setFichaRenderizada(null);
    try {
      const res = alvoSelecionado.tipo === "pessoa"
        ? await gerarFichaPessoa(inqueritoId, alvoSelecionado.id)
        : await gerarFichaEmpresa(inqueritoId, alvoSelecionado.id);
      setFichaRenderizada(res.ficha);
    } catch (e: any) {
      setErro(e?.response?.data?.detail || "Erro ao gerar ficha.");
    } finally { setGerando(false); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-20rem)]">
      <div className="flex flex-col gap-4">
        <Card className="bg-zinc-900 border-zinc-800 flex-1 flex flex-col">
          <CardHeader className="pb-3 border-b border-zinc-800">
            <CardTitle className="text-base flex items-center gap-2"><Target size={16} className="text-zinc-400" /> Alvos Mapeados</CardTitle>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              {loadingEntidades ? <div className="p-4 text-sm text-zinc-500">Buscando...</div> : (
                <div className="p-2 space-y-1">
                  {pessoas.length === 0 && empresas.length === 0 && <div className="p-4 text-sm text-zinc-500 text-center">Nenhuma entidade indexada.</div>}
                  {pessoas.length > 0 && <div className="px-3 py-1 text-xs font-semibold text-zinc-500 uppercase tracking-wider">Pessoas</div>}
                  {pessoas.map((p) => (
                    <button key={p.id} onClick={() => setAlvoSelecionado({id: p.id, tipo: "pessoa"})}
                      className={`w-full text-left px-3 py-2 rounded-md text-sm flex flex-col transition-colors ${alvoSelecionado?.id === p.id ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" : "text-zinc-300 hover:bg-zinc-800"}`}>
                      <div className="font-medium flex items-center gap-2"><User size={13}/> {p.nome}</div>
                      {p.cpf && <div className="text-xs text-zinc-500 mt-0.5">CPF: {p.cpf}</div>}
                    </button>
                  ))}
                  {empresas.length > 0 && <div className="px-3 py-1 text-xs font-semibold text-zinc-500 uppercase tracking-wider mt-2">Empresas</div>}
                  {empresas.map((e) => (
                    <button key={e.id} onClick={() => setAlvoSelecionado({id: e.id, tipo: "empresa"})}
                      className={`w-full text-left px-3 py-2 rounded-md text-sm flex flex-col transition-colors ${alvoSelecionado?.id === e.id ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" : "text-zinc-300 hover:bg-zinc-800"}`}>
                      <div className="font-medium flex items-center gap-2"><Building size={13}/> {e.nome}</div>
                      {e.cnpj && <div className="text-xs text-zinc-500 mt-0.5">CNPJ: {e.cnpj}</div>}
                    </button>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
        <Button className="w-full bg-blue-600 hover:bg-blue-700 h-11" disabled={!alvoSelecionado || gerando} onClick={handleGerarFicha}>
          {gerando ? <span className="flex items-center gap-2"><Bot className="animate-pulse" size={16}/> Processando...</span>
            : <span className="flex items-center gap-2"><UserSearch size={16}/> Emitir Ficha OSINT</span>}
        </Button>
      </div>

      <div className="lg:col-span-2">
        <Card className="bg-zinc-950 border-zinc-800 h-full flex flex-col shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />
          <CardHeader className="bg-zinc-900/50 border-b border-zinc-800 z-10">
            <CardTitle className="text-lg">Ficha de Inteligência Tática</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden p-0 z-10">
            <ScrollArea className="h-full">
              <div className="p-6">
                {erro ? (
                  <div className="bg-red-500/10 border border-red-500/20 rounded-md p-4 flex gap-3 text-red-400 items-start">
                    <AlertTriangle className="shrink-0 mt-0.5" size={16} />
                    <div className="text-sm">{erro}</div>
                  </div>
                ) : !fichaRenderizada && !gerando ? (
                  <div className="flex flex-col items-center justify-center h-64 text-zinc-500 text-center">
                    <Bot className="w-12 h-12 mb-4 text-zinc-800" />
                    <p className="text-sm">Selecione um alvo e mande o Agente processar.</p>
                  </div>
                ) : gerando ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3 text-zinc-400 text-sm">
                      <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                      Acessando bases e modelando grafo investigativo...
                    </div>
                    <div className="space-y-2 opacity-40">
                      {[3, 2, 4].map((w, i) => <div key={i} style={{width: `${w * 20}%`}} className="h-3 bg-zinc-800 rounded animate-pulse" />)}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <div>
                      <h2 className="text-xl font-bold text-zinc-100">{fichaRenderizada.nome || alvoSelecionado?.id}</h2>
                      <div className="flex gap-2 mt-2">
                        <Badge variant="outline" className="border-blue-500/30 text-blue-400 bg-blue-500/5">{fichaRenderizada.nivel_risco || fichaRenderizada.risco || "Desconhecido"}</Badge>
                        <Badge variant="outline" className="border-zinc-700 text-zinc-400 bg-zinc-800">LLM</Badge>
                      </div>
                    </div>
                    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">Resumo Executivo</h3>
                      <p className="text-zinc-300 text-sm leading-relaxed">{fichaRenderizada.perfil_resumido || fichaRenderizada.resumo || "Não disponível."}</p>
                    </div>
                    {fichaRenderizada.pontos_de_atencao?.length > 0 && (
                      <div>
                        <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide flex items-center gap-2 mb-2">
                          <AlertTriangle size={13} /> Pontos de Atenção
                        </h3>
                        <ul className="space-y-1.5">
                          {fichaRenderizada.pontos_de_atencao.map((b: string, i: number) => (
                            <li key={i} className="flex gap-2 text-sm text-zinc-300 bg-red-500/5 border border-red-500/10 p-2.5 rounded">
                              <span className="text-red-500 shrink-0">•</span> {b}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {fichaRenderizada.sugestoes_diligencias?.length > 0 && (
                      <div>
                        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Sugestões de Diligências</h3>
                        <ul className="space-y-1">
                          {fichaRenderizada.sugestoes_diligencias.map((d: string, i: number) => (
                            <li key={i} className="text-sm text-zinc-400 flex gap-2"><span className="text-blue-500 shrink-0">→</span> {d}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function AgenteOsintPage() {
  const { inqueritoAtivoId } = useAppStore();
  const [tab, setTab] = useState<"painel" | "ficha" | "cripto">("painel");

  if (!inqueritoAtivoId) {
    return (
      <div className="relative h-full flex items-center justify-center overflow-hidden bg-zinc-950">
        {/* Background Decorative */}
        <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-500/10 rounded-full blur-[120px] pointer-events-none" />
        <div className="absolute bottom-[-10%] left-[-10%] w-[30%] h-[30%] bg-orange-500/5 rounded-full blur-[100px] pointer-events-none" />

        <div className="relative z-10 flex flex-col items-center max-w-lg text-center p-8 animate-in fade-in zoom-in-95 duration-1000">
          <div className="mb-6 p-4 bg-zinc-900 border border-zinc-800 rounded-3xl shadow-2xl relative">
            <div className="absolute -top-3 -right-3">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
              </span>
            </div>
            <UserSearch className="w-16 h-16 text-blue-500 opacity-90" />
          </div>
          
          <h2 className="text-3xl font-extrabold tracking-tight text-white mb-3">
             Nenhum Inquérito Ativo
          </h2>
          <p className="text-zinc-400 text-base leading-relaxed mb-8">
            O Agente OSINT opera com base no contexto dos autos. Selecione um inquérito no seu Dashboard para iniciar a varredura automática de personagens.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 w-full">
            <Button 
               variant="outline" 
               className="flex-1 bg-zinc-900/50 border-zinc-800 hover:bg-zinc-800 text-zinc-100 h-12 text-base rounded-xl border-2 transition-all hover:scale-105"
               onClick={() => window.location.href = '/dashboard'}
            >
              Ir para o Dashboard
            </Button>
            <div className="flex-1 transition-all hover:scale-105">
              <ConsultaAvulsaDialog />
            </div>
          </div>
          
          <div className="mt-12 flex items-center gap-3 text-zinc-600">
            <Bot size={16} />
            <span className="text-xs uppercase tracking-[0.2em] font-semibold">Osint Intelligence Module v2.0</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <UserSearch className="text-blue-500" size={26} /> Agente OSINT
          </h1>
          <p className="text-zinc-400 mt-1 text-sm">Enriquecimento investigativo por personagem com dados externos (direct.data).</p>
        </div>
        <ConsultaAvulsaDialog />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-zinc-800">
        {([
          ["painel", "Personagens", UserSearch], 
          ["ficha", "Relatório OSINT", Bot],
          ["cripto", "Blockchain / Cripto", Wallet]
        ] as const).map(([t, label, Icon]) => (
          <button key={t} onClick={() => setTab(t as any)}
            className={`px-4 py-3 text-sm font-medium transition-all border-b-2 -mb-px flex items-center gap-2 ${
              tab === t ? "border-blue-500 text-zinc-100 bg-blue-500/5" : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}>
            <Icon size={14} className={tab === t ? "text-blue-500" : ""} />
            {label}
          </button>
        ))}
      </div>

      {/* Conteúdo */}
      <div className="relative">
        {tab === "painel" && <PainelPersonagens key={inqueritoAtivoId} inqueritoId={inqueritoAtivoId} />}
        {tab === "ficha" && <FichaIndividual key={inqueritoAtivoId} inqueritoId={inqueritoAtivoId} />}
        {tab === "cripto" && <InvestigacaoCripto />}
      </div>    </div>
  );
}
