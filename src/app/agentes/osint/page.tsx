"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/store/app";
import { api, getPessoas, getEmpresas, gerarFichaPessoa, gerarFichaEmpresa, osintConsultaAvulsa } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { UserSearch, Bot, Target, AlertTriangle, Building, User, Search, FileSearch, CheckCircle, XCircle, Phone, Mail, MapPin, Car, Shield, Briefcase } from "lucide-react";

// ── Componente: resultado de uma seção OSINT ──────────────────────────────────
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

// ── Componente: painel de resultado da consulta avulsa ────────────────────────
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
      {/* Fontes consultadas */}
      <div className="flex flex-wrap gap-1.5">
        {dados.fontes_consultadas?.map((f: string) => (
          <Badge key={f} variant="outline" className="text-xs border-green-700/40 text-green-400 bg-green-500/5">{f}</Badge>
        ))}
        {dados.fontes_sem_dados?.map((f: any) => (
          <Badge key={f.fonte} variant="outline" className="text-xs border-red-700/40 text-red-400 bg-red-500/5">{f.fonte}</Badge>
        ))}
      </div>

      {/* Qualificação */}
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

      {/* Alertas rápidos */}
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

      {/* Contatos */}
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

      {/* Endereços */}
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

      {/* Vínculos Empresariais (AML) */}
      {aml?.sociedades?.length > 0 && (
        <SecaoResultado titulo="Vínculos Empresariais" icone={Briefcase}>
          <div className="space-y-2">
            {aml.sociedades.map((s: any, i: number) => (
              <div key={i} className="bg-zinc-800/50 rounded p-2">
                <p className="text-xs font-medium text-zinc-200">{s.razaoSocial}</p>
                <div className="flex gap-2 mt-1 flex-wrap">
                  <Badge variant="outline" className="text-[10px] border-zinc-700 text-zinc-400">{s.cnpj}</Badge>
                  {s.socios?.find((so: any) => so.qualificacaoSocio) && (
                    <Badge variant="outline" className="text-[10px] border-blue-700/40 text-blue-400">
                      {s.socios.find((so: any) => so.cpf === aml.cpf)?.qualificacaoSocio || "Sócio"}
                    </Badge>
                  )}
                  {!s.baixada && <Badge variant="outline" className="text-[10px] border-green-700/40 text-green-400">Ativa</Badge>}
                </div>
              </div>
            ))}
          </div>
        </SecaoResultado>
      )}

      {/* Veículos (histórico por CPF) */}
      {veiculos && (
        <SecaoResultado titulo="Veículos" icone={Car}>
          {veiculos.veiculos?.length > 0 ? (
            <div className="space-y-1">
              {veiculos.veiculos.map((v: any, i: number) => (
                <div key={i} className="text-xs text-zinc-300">{v.placa} — {v.marca} {v.modelo} ({v.anoFabricacao})</div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-zinc-500">Nenhum veículo registrado</p>
          )}
        </SecaoResultado>
      )}

      {/* Veículo avulso por placa */}
      {veiculo && (
        <SecaoResultado titulo="Veículo Consultado" icone={Car}>
          <div className="text-xs space-y-1 text-zinc-300">
            {veiculo.placa && <p><span className="text-zinc-500">Placa:</span> {veiculo.placa}</p>}
            {veiculo.marca && <p><span className="text-zinc-500">Veículo:</span> {veiculo.marca} {veiculo.modelo} {veiculo.anoFabricacao}</p>}
            {veiculo.proprietario && <p><span className="text-zinc-500">Proprietário:</span> {veiculo.proprietario}</p>}
          </div>
        </SecaoResultado>
      )}

      {/* Receita Federal (CNPJ) */}
      {receita && (
        <SecaoResultado titulo="Receita Federal" icone={Building}>
          <div className="text-xs space-y-1 text-zinc-300">
            <p className="font-medium text-zinc-100">{receita.razaoSocial || receita.nomeFantasia}</p>
            {receita.situacaoCadastral && <p><span className="text-zinc-500">Situação:</span> {receita.situacaoCadastral}</p>}
            {receita.atividadePrincipal && <p><span className="text-zinc-500">Atividade:</span> {receita.atividadePrincipal}</p>}
          </div>
        </SecaoResultado>
      )}

      {/* Mandados por nome */}
      {mandadosNome && (
        <SecaoResultado titulo="Mandados por Nome" icone={Shield}>
          <StatusBadge ok={!mandadosNome.possuiMandado} label={mandadosNome.possuiMandado ? `${mandadosNome.mandadosPrisao?.length} mandado(s) ativo(s)` : "Sem mandados por este nome"} />
        </SecaoResultado>
      )}

      {/* Sem resultados */}
      {dados.fontes_consultadas?.length === 0 && (
        <p className="text-sm text-zinc-500 text-center py-4">Nenhuma fonte retornou dados.</p>
      )}
    </div>
  );
}

// ── Componente: Dialog de Consulta Avulsa ─────────────────────────────────────
function ConsultaAvulsaDialog() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ cpf: "", cnpj: "", placa: "", nome: "", data_nascimento: "", rg: "", uf: "RJ" });
  const [consultando, setConsultando] = useState(false);
  const [resultado, setResultado] = useState<any | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  const handleConsultar = async () => {
    const temDado = Object.entries(form).some(([k, v]) => k !== "uf" && v.trim() !== "");
    if (!temDado) return;

    setConsultando(true);
    setErro(null);
    setResultado(null);
    try {
      const res = await osintConsultaAvulsa(form);
      setResultado(res.dados);
    } catch (e: any) {
      setErro(e?.response?.data?.detail || "Erro na consulta.");
    } finally {
      setConsultando(false);
    }
  };

  const limpar = () => {
    setForm({ cpf: "", cnpj: "", placa: "", nome: "", data_nascimento: "", rg: "", uf: "RJ" });
    setResultado(null);
    setErro(null);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={
        <Button variant="outline" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 gap-2">
          <FileSearch size={15} /> Consulta Avulsa
        </Button>
      }>
        <FileSearch size={15} /> Consulta Avulsa
      </DialogTrigger>

      <DialogContent className="bg-zinc-950 border-zinc-800 max-w-4xl w-full max-h-[90vh] flex flex-col" showCloseButton={true}>
        <DialogHeader>
          <DialogTitle className="text-zinc-100 flex items-center gap-2">
            <FileSearch size={18} className="text-blue-400" />
            Consulta OSINT Avulsa
          </DialogTitle>
          <p className="text-xs text-zinc-500">Preencha ao menos um campo. Cada dado disponível desbloqueia APIs diferentes.</p>
        </DialogHeader>

        <div className="flex gap-6 flex-1 min-h-0 overflow-hidden mt-2">
          {/* Formulário */}
          <div className="w-72 shrink-0 space-y-4">
            <div className="space-y-3">
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">CPF <span className="text-zinc-600">(desbloqueia cadastro, mandados, AML...)</span></label>
                <Input value={form.cpf} onChange={e => set("cpf", e.target.value)}
                  placeholder="000.000.000-00" className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
              </div>
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">CNPJ <span className="text-zinc-600">(Receita Federal, sanções PJ)</span></label>
                <Input value={form.cnpj} onChange={e => set("cnpj", e.target.value)}
                  placeholder="00.000.000/0001-00" className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
              </div>
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Placa <span className="text-zinc-600">(dados do veículo)</span></label>
                <Input value={form.placa} onChange={e => set("placa", e.target.value.toUpperCase())}
                  placeholder="ABC1D23" className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
              </div>

              <div className="border-t border-zinc-800 pt-3">
                <p className="text-xs text-zinc-600 mb-2">Sem CPF — busca por identificação parcial:</p>
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">Nome</label>
                  <Input value={form.nome} onChange={e => set("nome", e.target.value)}
                    placeholder="Nome completo" className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
                </div>
                <div className="mt-2">
                  <label className="text-xs text-zinc-400 mb-1 block">RG</label>
                  <Input value={form.rg} onChange={e => set("rg", e.target.value)}
                    placeholder="0000000" className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
                </div>
                <div className="mt-2">
                  <label className="text-xs text-zinc-400 mb-1 block">Data de Nascimento</label>
                  <Input value={form.data_nascimento} onChange={e => set("data_nascimento", e.target.value)}
                    placeholder="DD/MM/AAAA" className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8" />
                </div>
                <div className="mt-2">
                  <label className="text-xs text-zinc-400 mb-1 block">UF <span className="text-zinc-600">(para antecedentes)</span></label>
                  <Input value={form.uf} onChange={e => set("uf", e.target.value.toUpperCase())}
                    placeholder="RJ" maxLength={2} className="bg-zinc-900 border-zinc-700 text-zinc-200 text-sm h-8 w-20" />
                </div>
              </div>
            </div>

            <div className="flex gap-2">
              <Button onClick={handleConsultar} disabled={consultando}
                className="flex-1 bg-blue-600 hover:bg-blue-700 h-9 text-sm gap-2">
                {consultando
                  ? <><div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Consultando...</>
                  : <><Search size={14} /> Consultar</>}
              </Button>
              {resultado && (
                <Button onClick={limpar} variant="outline"
                  className="border-zinc-700 text-zinc-400 hover:bg-zinc-800 h-9 text-sm px-3">
                  Limpar
                </Button>
              )}
            </div>
          </div>

          {/* Resultados */}
          <div className="flex-1 min-w-0 border-l border-zinc-800 pl-6 overflow-hidden">
            <ScrollArea className="h-full max-h-[65vh]">
              {!resultado && !erro && !consultando && (
                <div className="flex flex-col items-center justify-center h-48 text-zinc-600 text-center text-sm">
                  <Search className="w-10 h-10 mb-3 text-zinc-800" />
                  <p>Preencha os campos ao lado e clique em Consultar.</p>
                  <p className="text-xs mt-1">Qualquer combinação de dados é aceita.</p>
                </div>
              )}
              {consultando && (
                <div className="flex items-center gap-3 text-zinc-400 text-sm py-8 justify-center">
                  <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  Acessando bases de dados...
                </div>
              )}
              {erro && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex gap-3 text-red-400 text-sm">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {erro}
                </div>
              )}
              {resultado && <ResultadoAvulso dados={resultado} />}
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function AgenteOsintPage() {
  const { inqueritoAtivoId } = useAppStore();
  const [pessoas, setPessoas] = useState<any[]>([]);
  const [empresas, setEmpresas] = useState<any[]>([]);
  const [loadingEntidades, setLoadingEntidades] = useState(false);
  const [alvoSelecionado, setAlvoSelecionado] = useState<{id: string, tipo: "pessoa" | "empresa"} | null>(null);
  const [gerando, setGerando] = useState(false);
  const [fichaRenderizada, setFichaRenderizada] = useState<any | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (inqueritoAtivoId) {
      setLoadingEntidades(true);
      Promise.all([
        getPessoas(inqueritoAtivoId).catch(() => []),
        getEmpresas(inqueritoAtivoId).catch(() => [])
      ]).then(([p, e]) => {
        setPessoas(p);
        setEmpresas(e);
      }).finally(() => setLoadingEntidades(false));
    } else {
      setPessoas([]);
      setEmpresas([]);
    }
  }, [inqueritoAtivoId]);

  const handleGerarFicha = async () => {
    if (!alvoSelecionado || !inqueritoAtivoId) return;
    setGerando(true);
    setErro(null);
    setFichaRenderizada(null);
    try {
      let res;
      if (alvoSelecionado.tipo === "pessoa") {
        res = await gerarFichaPessoa(inqueritoAtivoId, alvoSelecionado.id);
      } else {
        res = await gerarFichaEmpresa(inqueritoAtivoId, alvoSelecionado.id);
      }
      setFichaRenderizada(res.ficha);
    } catch (e: any) {
      setErro(e?.response?.data?.detail || "Ocorreu um erro ao gerar a ficha OSINT.");
    } finally {
      setGerando(false);
    }
  };

  if (!inqueritoAtivoId) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center text-zinc-500">
        <UserSearch className="w-16 h-16 mb-4 text-zinc-700" />
        <h2 className="text-xl font-medium text-zinc-300">Nenhum inquérito selecionado</h2>
        <p className="mt-2 max-w-md">Para utilizar o Agente Investigativo OSINT, selecione um inquérito ativo no Dashboard primeiro.</p>
        <div className="mt-6">
          <ConsultaAvulsaDialog />
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 h-[calc(100vh-2rem)] flex flex-col">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <UserSearch className="text-blue-500" />
            Agente OSINT
          </h1>
          <p className="text-zinc-400 mt-2">
            Gere perfis investigativos profundos de pessoas ou empresas cruzando fontes abertas e contexto dos autos.
          </p>
        </div>
        <ConsultaAvulsaDialog />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 flex-1 min-h-0">
        {/* Coluna Esquerda: Alvos */}
        <div className="flex flex-col gap-4">
          <Card className="bg-zinc-900 border-zinc-800 flex-1 flex flex-col">
            <CardHeader className="pb-3 border-b border-zinc-800">
              <CardTitle className="text-lg flex items-center gap-2">
                <Target size={18} className="text-zinc-400" />
                Alvos Mapeados
              </CardTitle>
              <CardDescription>Entidades identificadas no Inquérito</CardDescription>
            </CardHeader>
            <CardContent className="p-0 flex-1 overflow-hidden">
              <ScrollArea className="h-full">
                {loadingEntidades ? (
                  <div className="p-4 text-sm text-zinc-500">Buscando entidades...</div>
                ) : (
                  <div className="p-2 space-y-1">
                    {pessoas.length === 0 && empresas.length === 0 && (
                      <div className="p-4 text-sm text-zinc-500 text-center">Nenhuma entidade indexada.</div>
                    )}
                    {pessoas.length > 0 && <div className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider">Pessoas</div>}
                    {pessoas.map((p) => (
                      <button key={p.id} onClick={() => setAlvoSelecionado({id: p.id, tipo: "pessoa"})}
                        className={`w-full text-left px-3 py-2 rounded-md text-sm flex flex-col transition-colors ${
                          alvoSelecionado?.id === p.id ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" : "text-zinc-300 hover:bg-zinc-800"
                        }`}>
                        <div className="font-medium flex items-center gap-2"><User size={14}/> {p.nome}</div>
                        {p.cpf && <div className="text-xs text-zinc-500 mt-1">CPF: {p.cpf}</div>}
                      </button>
                    ))}
                    {empresas.length > 0 && <div className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider mt-2">Empresas</div>}
                    {empresas.map((e) => (
                      <button key={e.id} onClick={() => setAlvoSelecionado({id: e.id, tipo: "empresa"})}
                        className={`w-full text-left px-3 py-2 rounded-md text-sm flex flex-col transition-colors ${
                          alvoSelecionado?.id === e.id ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" : "text-zinc-300 hover:bg-zinc-800"
                        }`}>
                        <div className="font-medium flex items-center gap-2"><Building size={14}/> {e.nome}</div>
                        {e.cnpj && <div className="text-xs text-zinc-500 mt-1">CNPJ: {e.cnpj}</div>}
                      </button>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>

          <Button className="w-full bg-blue-600 hover:bg-blue-700 h-12"
            disabled={!alvoSelecionado || gerando} onClick={handleGerarFicha}>
            {gerando ? (
              <span className="flex items-center gap-2"><Bot className="animate-pulse" size={18}/> Processando Inteligência...</span>
            ) : (
              <span className="flex items-center gap-2"><UserSearch size={18}/> Emitir Ficha OSINT</span>
            )}
          </Button>
        </div>

        {/* Coluna Direita: Dossiê */}
        <div className="lg:col-span-2 flex flex-col">
          <Card className="bg-zinc-950 border-zinc-800 h-full flex flex-col shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />
            <CardHeader className="bg-zinc-900/50 border-b border-zinc-800 z-10">
              <CardTitle className="text-xl">Ficha de Inteligência Tática</CardTitle>
              <CardDescription>O resultado do levantamento aparecerá abaixo</CardDescription>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden p-0 z-10">
              <ScrollArea className="h-full">
                <div className="p-6">
                  {erro ? (
                    <div className="bg-red-500/10 border border-red-500/20 rounded-md p-4 flex gap-3 text-red-400 items-start">
                      <AlertTriangle className="shrink-0 mt-0.5" size={18} />
                      <div className="text-sm">{erro}</div>
                    </div>
                  ) : !fichaRenderizada && !gerando ? (
                    <div className="flex flex-col items-center justify-center h-64 text-zinc-500 text-center">
                      <Bot className="w-12 h-12 mb-4 text-zinc-800" />
                      <p>Selecione um alvo na lista ao lado e mande o Agente processar.</p>
                    </div>
                  ) : gerando ? (
                    <div className="space-y-6">
                      <div className="flex items-center gap-4 text-zinc-400">
                        <div className="w-6 h-6 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                        Acessando bases de dados e modelando grafo investigativo...
                      </div>
                      <div className="space-y-2 opacity-50">
                        <div className="h-4 w-3/4 bg-zinc-800 rounded animate-pulse" />
                        <div className="h-4 w-1/2 bg-zinc-800 rounded animate-pulse" />
                        <div className="h-4 w-5/6 bg-zinc-800 rounded animate-pulse" />
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                      <div className="flex justify-between items-start">
                        <div>
                          <h2 className="text-2xl font-bold text-zinc-100">{fichaRenderizada.nome || alvoSelecionado?.id}</h2>
                          <div className="flex gap-2 mt-2">
                            <Badge variant="outline" className="border-blue-500/30 text-blue-400 bg-blue-500/5">
                              {fichaRenderizada.nivel_risco || fichaRenderizada.risco || "Desconhecido"}
                            </Badge>
                            <Badge variant="outline" className="border-zinc-700 text-zinc-400 bg-zinc-800">Gerado por LLM</Badge>
                          </div>
                        </div>
                      </div>
                      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
                        <h3 className="text-sm font-semibold text-zinc-100 uppercase tracking-wide mb-3">Resumo Executivo</h3>
                        <p className="text-zinc-300 text-sm leading-relaxed">{fichaRenderizada.perfil_resumido || fichaRenderizada.resumo || "Não disponível."}</p>
                      </div>
                      {fichaRenderizada.pontos_de_atencao?.length > 0 && (
                        <div>
                          <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wide flex items-center gap-2 mb-3">
                            <AlertTriangle size={16} /> Pontos de Atenção
                          </h3>
                          <ul className="space-y-2">
                            {fichaRenderizada.pontos_de_atencao.map((b: string, i: number) => (
                              <li key={i} className="flex gap-2 text-sm text-zinc-300 bg-red-500/5 border border-red-500/10 p-3 rounded">
                                <span className="text-red-500 shrink-0">•</span> {b}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {fichaRenderizada.sugestoes_diligencias?.length > 0 && (
                        <div>
                          <h3 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Sugestões de Diligências</h3>
                          <ul className="space-y-1">
                            {fichaRenderizada.sugestoes_diligencias.map((d: string, i: number) => (
                              <li key={i} className="text-sm text-zinc-400 flex gap-2">
                                <span className="text-blue-500 shrink-0">→</span> {d}
                              </li>
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
    </div>
  );
}
