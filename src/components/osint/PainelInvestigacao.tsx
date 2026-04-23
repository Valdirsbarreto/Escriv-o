"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  User, Building, ChevronDown, ChevronRight, Loader2,
  AlertTriangle, CheckCircle, XCircle, MinusCircle,
  ExternalLink, Play, UserSearch, Globe, Scale, Newspaper, FileText,
} from "lucide-react";
import { osintSugestao, osintLote, osintAnalisePreliminar, osintBuscaWeb, osintGerarRelatorioWeb, osintGratuito, osintDeepResearch, osintDeepStatus, osintDeepPlanejar, osintDeepExecutar } from "@/lib/api";
import { Sparkles, Zap, Microscope } from "lucide-react";

// ── Tipos ─────────────────────────────────────────────────────────────────────

type Staleness = "fresco" | "desatualizado" | "ausente";

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
}

interface PersonagemAnalise {
  pessoa_id: string;
  nome: string;
  tipo_pessoa: string;
  cpf?: string | null;
  cnpj?: string | null;
  perfil_sugerido: number | null;
  justificativa: string;
  dados_nos_autos: {
    cpf: DadoCampo;
    telefone: DadoCampo;
    endereco: DadoCampo;
  };
  historico_inqueritos: HistoricoInquerito[];
  osint_realizado: boolean;
}

// ── Modal de confirmação para consultas pagas ─────────────────────────────────

function ModalConfirmacaoOSINT({
  nomePessoa,
  modulosSelecionados,
  custo,
  onConfirm,
  onCancel,
}: {
  nomePessoa: string;
  modulosSelecionados: { label: string; custo: number }[];
  custo: number;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-full max-w-sm mx-4 p-5 space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Confirmar consulta OSINT</h3>
          <p className="text-xs text-zinc-400 mt-0.5 truncate">{nomePessoa}</p>
        </div>

        <div className="space-y-1">
          <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1.5">Módulos selecionados</p>
          {modulosSelecionados.map((m, i) => (
            <div key={i} className="flex items-center justify-between text-xs">
              <span className="text-zinc-300">{m.label}</span>
              <span className="font-mono text-zinc-400">R$ {m.custo.toFixed(2)}</span>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-zinc-800 pt-3">
          <div>
            <p className="text-xs text-zinc-500">Total a debitar</p>
            <p className="text-lg font-mono font-bold text-zinc-100">R$ {custo.toFixed(2)}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              className="px-3 py-1.5 text-xs rounded-lg border border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300 transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={onConfirm}
              className="px-3 py-1.5 text-xs rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
            >
              Confirmar consulta
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Constantes ────────────────────────────────────────────────────────────────

const OSINT_MODULOS = [
  { id: "cadastro_pf_plus",      label: "Cadastro Plus",         custo: 2.50, color: "text-green-400" },
  { id: "vinculo_empregaticio",  label: "Vínculo CLT / RH",      custo: 3.10, color: "text-green-400" },
  { id: "historico_veiculos_pf", label: "Histórico Veicular",    custo: 0.90, color: "text-lime-400" },
  { id: "bpc",                   label: "Benefícios BPC",        custo: 1.50, color: "text-blue-400" },
  { id: "mandados_prisao",       label: "Mandados de Prisão",    custo: 1.20, color: "text-red-400" },
  { id: "pep",                   label: "Pessoa Exposta (PEP)",  custo: 0.72, color: "text-yellow-400" },
  { id: "aml",                   label: "AML / Lavagem",         custo: 0.72, color: "text-orange-400" },
  { id: "ceis",                  label: "CEIS (Inidôneas)",      custo: 0.36, color: "text-orange-400" },
  { id: "cnep",                  label: "CNEP (Punidas)",        custo: 0.36, color: "text-orange-400" },
  { id: "processos_tj",          label: "Processos TJ",         custo: 2.00, color: "text-red-400" },
  { id: "ofac",                  label: "Lista OFAC",            custo: 0.36, color: "text-red-400" },
  { id: "lista_onu",             label: "Lista ONU",             custo: 0.36, color: "text-red-400" },
];

const initSugestao = (perfil: number | null): string[] => {
  if (perfil === 1) return ["cadastro_pf_plus", "historico_veiculos_pf"];
  if (perfil === 2) return ["cadastro_pf_plus", "historico_veiculos_pf", "mandados_prisao", "pep"];
  if (perfil === 3) return ["cadastro_pf_plus", "historico_veiculos_pf", "mandados_prisao", "aml", "ceis"];
  if (perfil === 4) return ["cadastro_pf_plus", "vinculo_empregaticio", "historico_veiculos_pf", "mandados_prisao", "aml", "processos_tj"];
  return [];
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function DadosBadge({ campo, label }: { campo: DadoCampo; label: string }) {
  const cor = campo.staleness === "fresco"
    ? "border-green-600/50 text-green-400 bg-green-500/10"
    : campo.staleness === "desatualizado"
    ? "border-yellow-600/50 text-yellow-400 bg-yellow-500/10"
    : "border-zinc-600 text-zinc-400 bg-zinc-800/60";
  return (
    <span title={campo.texto ? `${label}: "${campo.texto}"` : `${label}: não informado`}
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs border cursor-default ${cor}`}>
      {label}
    </span>
  );
}

function TipoPessoa({ tipo }: { tipo: string }) {
  const cor = tipo === "investigado" ? "border-red-700/40 text-red-400"
    : tipo === "vitima" ? "border-blue-700/40 text-blue-400"
    : tipo === "testemunha" ? "border-yellow-700/40 text-yellow-400"
    : "border-zinc-700 text-zinc-400";
  return (
    <Badge variant="outline" className={`text-xs capitalize ${cor}`}>{tipo}</Badge>
  );
}

// ── Card de Personagem ────────────────────────────────────────────────────────

// ── Componente OSINT Fontes Abertas (Serper.dev) ──────────────────────────────

// ── Painel OSINT Gratuito (Receita Federal + CGU) ─────────────────────────────

function OsintGratuitoPanel({ inqueritoId, pessoaId }: { inqueritoId: string; pessoaId: string }) {
  const [dados, setDados] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [erroMsg, setErroMsg] = useState<string | null>(null);
  const [aberto, setAberto] = useState(false);

  const handleBuscar = async () => {
    if (dados) { setAberto(v => !v); return; }
    setLoading(true);
    setAberto(true);
    setErroMsg(null);
    try {
      const r = await osintGratuito(inqueritoId, pessoaId);
      setDados(r.dados_gratuitos);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Erro desconhecido";
      setErroMsg(String(detail));
    } finally { setLoading(false); }
  };

  const situacaoCor = (s: string) => {
    if (!s) return "text-zinc-500";
    const sl = s.toLowerCase();
    if (sl.includes("ativa")) return "text-emerald-400";
    if (sl.includes("inapta") || sl.includes("suspensa")) return "text-yellow-400";
    if (sl.includes("baixada") || sl.includes("cancelada")) return "text-red-400";
    return "text-zinc-400";
  };

  return (
    <div className="rounded-lg border border-emerald-800/40 bg-zinc-900/60 overflow-hidden">
      {/* Cabeçalho */}
      <button
        onClick={handleBuscar}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-zinc-800/40 transition-colors"
      >
        <div className="flex items-center gap-1.5">
          <Scale size={11} className="text-emerald-400" />
          <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">Dados Públicos</span>
          <span className="text-xs text-zinc-600">Receita Federal · CGU</span>
          <span className="text-xs text-emerald-700 font-medium bg-emerald-950/50 px-1.5 py-0.5 rounded">grátis</span>
        </div>
        {loading
          ? <Loader2 size={11} className="text-emerald-400 animate-spin" />
          : <ChevronRight size={11} className={`text-zinc-500 transition-transform ${aberto ? "rotate-90" : ""}`} />
        }
      </button>

      {/* Conteúdo */}
      {aberto && (
        <div className="px-3 pb-3 space-y-2 border-t border-zinc-800/60">
          {loading && (
            <p className="text-xs text-zinc-500 py-2">Consultando Receita Federal...</p>
          )}

          {erroMsg && (
            <p className="text-xs text-red-400 py-1">{erroMsg}</p>
          )}

          {dados && (
            <>
              {/* Resumo */}
              {dados.resumo && (
                <p className="text-sm text-zinc-300 leading-relaxed pt-2">{dados.resumo}</p>
              )}

              {/* Situação cadastral */}
              {dados.situacao_cadastral && dados.situacao_cadastral !== "outro" && (
                <div className="flex items-center gap-2 pt-1">
                  <span className="text-xs text-zinc-500">Situação:</span>
                  <span className={`text-xs font-bold uppercase ${situacaoCor(dados.situacao_cadastral)}`}>
                    {dados.situacao_cadastral}
                  </span>
                </div>
              )}

              {/* Alertas */}
              {dados.alertas?.length > 0 && (
                <div className="space-y-1 pt-1">
                  <p className="text-xs text-zinc-600 uppercase tracking-wider flex items-center gap-1">
                    <AlertTriangle size={9} className="text-red-400" /> Alertas
                  </p>
                  {dados.alertas.map((a: string, i: number) => (
                    <p key={i} className="text-xs text-red-300 pl-3">• {a}</p>
                  ))}
                </div>
              )}

              {/* Sanções */}
              {dados.sancoes_encontradas?.length > 0 && (
                <div className="space-y-1 pt-1">
                  <p className="text-xs text-zinc-600 uppercase tracking-wider flex items-center gap-1">
                    <XCircle size={9} className="text-orange-400" /> Sanções CGU/CEIS
                  </p>
                  {dados.sancoes_encontradas.map((s: any, i: number) => (
                    <p key={i} className="text-xs text-orange-300 pl-3">
                      • {s.tipo} — {s.orgao} ({s.periodo})
                    </p>
                  ))}
                </div>
              )}

              {/* Sócios de interesse */}
              {dados.socios_de_interesse?.length > 0 && (
                <div className="space-y-1 pt-1">
                  <p className="text-xs text-zinc-600 uppercase tracking-wider">Quadro Societário</p>
                  {dados.socios_de_interesse.map((s: any, i: number) => (
                    <div key={i} className="pl-3">
                      <p className="text-xs text-zinc-300">
                        • <span className="font-medium">{s.nome}</span>
                        {s.cpf_cnpj && <span className="text-zinc-500"> — {s.cpf_cnpj}</span>}
                        <span className="text-zinc-600"> ({s.qualificacao})</span>
                      </p>
                      {s.observacao && (
                        <p className="text-xs text-yellow-400 pl-3">{s.observacao}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Correlações */}
              {dados.correlacoes_com_autos?.length > 0 && (
                <div className="space-y-1 pt-1">
                  <p className="text-xs text-zinc-600 uppercase tracking-wider flex items-center gap-1">
                    <CheckCircle size={9} className="text-blue-400" /> Correlações com os autos
                  </p>
                  {dados.correlacoes_com_autos.map((c: string, i: number) => (
                    <p key={i} className="text-xs text-blue-300 pl-3">• {c}</p>
                  ))}
                </div>
              )}

              {/* Dados úteis para diligência */}
              {dados.dados_uteis_para_diligencia?.length > 0 && (
                <div className="space-y-1 pt-1">
                  <p className="text-xs text-zinc-600 uppercase tracking-wider">Dados para diligência</p>
                  {dados.dados_uteis_para_diligencia.map((d: string, i: number) => (
                    <p key={i} className="text-xs text-zinc-400 pl-3">• {d}</p>
                  ))}
                </div>
              )}

              {/* Sugestão de consulta paga */}
              {dados.sugestoes_consulta_paga?.length > 0 && dados.sugestoes_consulta_paga[0] !== "" && (
                <div className="space-y-1 pt-1 border-t border-zinc-800/40">
                  <p className="text-xs text-zinc-600 uppercase tracking-wider">Recomenda consulta paga</p>
                  {dados.sugestoes_consulta_paga.map((s: string, i: number) => (
                    <p key={i} className="text-xs text-zinc-500 pl-3">• {s}</p>
                  ))}
                </div>
              )}

              {/* Rodapé */}
              <p className="text-xs text-zinc-700 pt-1">
                via BrasilAPI / Receita Federal · cache 12h · custo R$0,00
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Painel OSINT Fontes Abertas (Serper.dev) ──────────────────────────────────

function OsintWebPanel({ inqueritoId, pessoaId }: { inqueritoId: string; pessoaId: string }) {
  const [dados, setDados] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [erroMsg, setErroMsg] = useState<string | null>(null);
  const [aberto, setAberto] = useState(false);
  const [gerandoRelatorio, setGerandoRelatorio] = useState(false);
  const [relatorioOk, setRelatorioOk] = useState(false);

  const handleBuscar = async () => {
    if (dados) { setAberto(v => !v); return; }
    setLoading(true);
    setAberto(true);
    setErroMsg(null);
    try {
      const r = await osintBuscaWeb(inqueritoId, pessoaId);
      setDados(r.dados_web);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Erro desconhecido";
      console.error("[OsintWeb] erro:", e?.response?.status, detail);
      setErroMsg(String(detail));
    } finally { setLoading(false); }
  };

  const presencaCor = (p: string) =>
    p === "alta" ? "text-red-400" : p === "moderada" ? "text-yellow-400" : "text-zinc-500";

  return (
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-900/60 overflow-hidden">
      {/* Cabeçalho / botão */}
      <button
        onClick={handleBuscar}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-zinc-800/40 transition-colors"
      >
        <div className="flex items-center gap-1.5">
          <Globe size={11} className="text-sky-400" />
          <span className="text-xs font-bold text-sky-400 uppercase tracking-wider">Fontes Abertas</span>
          <span className="text-xs text-zinc-600">(web)</span>
          {dados && (
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-sky-500/10 border border-sky-700/30 text-sky-400">
              {dados.total_resultados} resultados
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {loading && <Loader2 size={10} className="animate-spin text-sky-400" />}
          {!loading && (aberto ? <ChevronDown size={11} className="text-zinc-600" /> : <ChevronRight size={11} className="text-zinc-600" />)}
        </div>
      </button>

      {/* Conteúdo expandido */}
      {aberto && (
        <div className="border-t border-zinc-800 px-3 py-3 space-y-3">
          {loading ? (
            <div className="flex items-center gap-2 text-zinc-500 text-xs py-2">
              <Loader2 size={12} className="animate-spin text-sky-400" />
              Buscando em fontes abertas...
            </div>
          ) : erroMsg ? (
            <p className="text-xs text-red-400/70 italic">Erro: {erroMsg}</p>
          ) : dados ? (
            <>
              {/* Resumo */}
              {dados.resumo_web && (
                <div className="flex items-start gap-2">
                  {dados.presenca_digital && (
                    <span className={`shrink-0 text-xs font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border border-current/20 ${presencaCor(dados.presenca_digital)}`}>
                      {dados.presenca_digital}
                    </span>
                  )}
                  <p className="text-xs text-zinc-300 leading-relaxed">{dados.resumo_web}</p>
                </div>
              )}

              {/* Alertas */}
              {dados.alertas?.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1 flex items-center gap-1">
                    <AlertTriangle size={9} className="text-red-400" /> Alertas
                  </p>
                  <ul className="space-y-0.5">
                    {dados.alertas.slice(0, 4).map((a: string, i: number) => (
                      <li key={i} className="text-xs text-red-300/80 flex gap-1.5">
                        <span className="text-red-500 shrink-0 mt-0.5">⚠</span>{a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Menções jurídicas */}
              {dados.mencoes_juridicas?.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1 flex items-center gap-1">
                    <Scale size={9} className="text-blue-400" /> Menções Jurídicas
                  </p>
                  <ul className="space-y-0.5">
                    {dados.mencoes_juridicas.slice(0, 3).map((m: string, i: number) => (
                      <li key={i} className="text-xs text-blue-300/80 flex gap-1.5">
                        <span className="text-blue-600 shrink-0 mt-0.5">▸</span>{m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Menções oficiais */}
              {dados.mencoes_oficiais?.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1 flex items-center gap-1">
                    <FileText size={9} className="text-amber-400" /> Menções Oficiais
                  </p>
                  <ul className="space-y-0.5">
                    {dados.mencoes_oficiais.slice(0, 3).map((m: string, i: number) => (
                      <li key={i} className="text-xs text-amber-300/80 flex gap-1.5">
                        <span className="text-amber-600 shrink-0 mt-0.5">▸</span>{m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Correlações com autos */}
              {dados.correlacoes_com_autos?.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1">Correlações com os autos</p>
                  <ul className="space-y-0.5">
                    {dados.correlacoes_com_autos.slice(0, 3).map((c: string, i: number) => (
                      <li key={i} className="text-xs text-emerald-300/80 flex gap-1.5">
                        <span className="text-emerald-600 shrink-0 mt-0.5">↔</span>{c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Fontes com links */}
              {dados.fontes_relevantes?.length > 0 && (
                <div className="border-t border-zinc-800 pt-2">
                  <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <Newspaper size={9} /> Fontes
                  </p>
                  <div className="space-y-1">
                    {dados.fontes_relevantes.slice(0, 5).map((f: any, i: number) => (
                      <a
                        key={i}
                        href={f.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-start gap-1.5 group"
                      >
                        <ExternalLink size={9} className="text-zinc-600 group-hover:text-sky-400 shrink-0 mt-0.5 transition-colors" />
                        <div className="min-w-0">
                          <p className="text-xs text-zinc-400 group-hover:text-sky-400 truncate transition-colors">{f.titulo}</p>
                          {f.trecho && <p className="text-xs text-zinc-600 line-clamp-1">{f.trecho}</p>}
                        </div>
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* Botão gerar relatório formal */}
              <div className="flex items-center justify-between pt-1 border-t border-zinc-800 mt-1">
                <p className="text-xs text-zinc-700">via serper.dev</p>
                {relatorioOk ? (
                  <span className="text-xs text-green-500 flex items-center gap-1">
                    <CheckCircle size={9} /> Relatório salvo nos documentos
                  </span>
                ) : (
                  <button
                    onClick={async () => {
                      setGerandoRelatorio(true);
                      try {
                        await osintGerarRelatorioWeb(inqueritoId, pessoaId);
                        setRelatorioOk(true);
                      } catch (e: any) {
                        alert(e?.response?.data?.detail || "Erro ao gerar relatório.");
                      } finally {
                        setGerandoRelatorio(false);
                      }
                    }}
                    disabled={gerandoRelatorio}
                    className="flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 disabled:opacity-50 transition-colors"
                  >
                    {gerandoRelatorio
                      ? <><Loader2 size={9} className="animate-spin" /> Gerando...</>
                      : <><FileText size={9} /> Gerar Relatório Formal</>}
                  </button>
                )}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

// ── Componente de análise preliminar ─────────────────────────────────────────

function AnalisePreliminarPanel({
  inqueritoId, pessoaId,
}: { inqueritoId: string; pessoaId: string }) {
  const [analise, setAnalise] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [aprimorando, setAprimorando] = useState(false);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    osintAnalisePreliminar(inqueritoId, pessoaId, false)
      .then(r => setAnalise(r.analise))
      .catch(() => setErro(true))
      .finally(() => setLoading(false));
  }, [inqueritoId, pessoaId]);

  const handleAprimorar = async () => {
    setAprimorando(true);
    try {
      const r = await osintAnalisePreliminar(inqueritoId, pessoaId, true);
      setAnalise(r.analise);
    } catch { /* silencioso */ } finally { setAprimorando(false); }
  };

  const corRisco = (nivel: string) =>
    nivel === "critico" ? "text-red-400 border-red-700/40 bg-red-500/5"
    : nivel === "alto"   ? "text-orange-400 border-orange-700/40 bg-orange-500/5"
    : nivel === "medio"  ? "text-yellow-400 border-yellow-700/40 bg-yellow-500/5"
    : "text-green-400 border-green-700/40 bg-green-500/5";

  return (
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-900/60 overflow-hidden">
      {/* Cabeçalho da seção */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-zinc-900/80">
        <div className="flex items-center gap-1.5">
          <Zap size={11} className="text-emerald-400" />
          <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
            Análise Preliminar
          </span>
          <span className="text-xs text-zinc-600">(LLM gratuita)</span>
        </div>
        {analise && (
          <button
            onClick={handleAprimorar}
            disabled={aprimorando}
            className="flex items-center gap-1 text-xs px-2 py-0.5 rounded border border-blue-700/30 text-blue-400 bg-blue-500/5 hover:bg-blue-500/10 transition-colors disabled:opacity-50"
          >
            {aprimorando
              ? <><Loader2 size={9} className="animate-spin" /> Aprimorando...</>
              : <><Sparkles size={9} /> Aprimorar (Gemini Flash)</>}
          </button>
        )}
      </div>

      {/* Conteúdo */}
      <div className="px-3 py-3 space-y-2.5">
        {loading ? (
          <div className="flex items-center gap-2 text-zinc-500 text-xs py-2">
            <Loader2 size={12} className="animate-spin text-emerald-400" />
            Analisando dados dos autos...
          </div>
        ) : erro ? (
          <p className="text-xs text-zinc-600 italic">Análise não disponível — dados insuficientes nos autos.</p>
        ) : analise ? (
          <>
            {/* Resumo + risco */}
            <div className="flex items-start gap-2">
              {analise.nivel_risco && (
                <span className={`shrink-0 text-xs font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider ${corRisco(analise.nivel_risco)}`}>
                  {analise.nivel_risco}
                </span>
              )}
              <p className="text-xs text-zinc-300 leading-relaxed">{analise.resumo}</p>
            </div>

            {/* Fatos conhecidos */}
            {analise.fatos_conhecidos?.length > 0 && (
              <div>
                <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1">Fatos nos autos</p>
                <ul className="space-y-0.5">
                  {analise.fatos_conhecidos.slice(0, 4).map((f: string, i: number) => (
                    <li key={i} className="text-xs text-zinc-400 flex gap-1.5">
                      <span className="text-emerald-600 shrink-0 mt-0.5">▸</span>{f}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Pontos de atenção */}
            {analise.pontos_de_atencao?.length > 0 && (
              <div>
                <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1">Pontos de atenção</p>
                <ul className="space-y-0.5">
                  {analise.pontos_de_atencao.slice(0, 3).map((pt: string, i: number) => (
                    <li key={i} className="text-xs text-orange-300/80 flex gap-1.5">
                      <span className="text-orange-500 shrink-0 mt-0.5">⚠</span>{pt}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Lacunas → justifica OSINT pago */}
            {analise.lacunas?.length > 0 && (
              <div className="border-t border-zinc-800 pt-2">
                <p className="text-xs text-zinc-600 uppercase tracking-wider mb-1">Lacunas → justificam consulta externa</p>
                <ul className="space-y-0.5">
                  {analise.lacunas.slice(0, 3).map((l: string, i: number) => (
                    <li key={i} className="text-xs text-zinc-500 flex gap-1.5">
                      <span className="text-zinc-700 shrink-0">→</span>{l}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {analise._fonte && (
              <p className="text-xs text-zinc-700 text-right">via {analise._fonte}</p>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}

// ── OSINT Deep Research Panel ─────────────────────────────────────────────────

function OsintDeepPanel({ inqueritoId, pessoaId, nomePessoa, onVerRelatorio }: {
  inqueritoId: string;
  pessoaId: string;
  nomePessoa: string;
  onVerRelatorio?: () => void;
}) {
  type Etapa = "carregando" | "idle" | "planejando" | "revisando" | "iniciado" | "concluido" | "erro";
  const [etapa, setEtapa] = useState<Etapa>("carregando");
  const [erroMsg, setErroMsg] = useState<string | null>(null);
  const [docId, setDocId] = useState<string | null>(null);
  const [briefing, setBriefing] = useState("");

  // Restaura estado após navegação
  useEffect(() => {
    osintDeepStatus(inqueritoId, pessoaId)
      .then(r => {
        setDocId(r.doc_id);
        if (r.status === "processando") setEtapa("iniciado");
        else if (r.status === "concluido") setEtapa("concluido");
        else if (r.status === "erro") { setEtapa("erro"); setErroMsg(r.erro || "Erro na pesquisa."); }
        else setEtapa("idle");
      })
      .catch(() => setEtapa("idle"));
  }, [inqueritoId, pessoaId]);

  const handlePlanejar = async () => {
    setEtapa("planejando");
    setErroMsg(null);
    try {
      const r = await osintDeepPlanejar(inqueritoId, pessoaId);
      setBriefing(r.briefing);
      setEtapa("revisando");
    } catch (e: any) {
      setErroMsg(e?.response?.data?.detail || e?.message || "Erro ao gerar plano.");
      setEtapa("erro");
    }
  };

  const handleExecutar = async () => {
    setEtapa("iniciado");
    setErroMsg(null);
    try {
      const r = await osintDeepExecutar(inqueritoId, pessoaId, briefing);
      setDocId(r.doc_id);
    } catch (e: any) {
      if (e?.response?.status === 409) { setEtapa("iniciado"); return; }
      setErroMsg(e?.response?.data?.detail || e?.message || "Erro ao iniciar pesquisa.");
      setEtapa("erro");
    }
  };

  return (
    <div className="rounded-lg border border-violet-800/40 bg-zinc-900/60 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2">
        <Microscope size={11} className="text-violet-400 shrink-0" />
        <span className="text-xs font-bold text-violet-400 uppercase tracking-wider">Deep Research</span>
        <span className="text-xs text-zinc-600">Gemini · 5–15 min · ~US$ 1–3</span>
      </div>
      <div className="px-3 pb-3 border-t border-zinc-800/60 pt-2 space-y-2">

        {erroMsg && (
          <p className="text-xs text-red-400 leading-relaxed">{erroMsg}</p>
        )}

        {etapa === "carregando" && (
          <div className="flex items-center gap-1.5 text-xs text-zinc-600">
            <Loader2 size={10} className="animate-spin" /> verificando…
          </div>
        )}

        {etapa === "idle" && (
          <>
            <p className="text-xs text-zinc-500 leading-relaxed">
              Pesquisa autônoma em fontes abertas: processos, patrimônio, empresas, mídia, sanções.
              O relatório é salvo em <span className="text-zinc-300">Documentos IA</span>.
            </p>
            <button
              onClick={handlePlanejar}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-violet-700/50 text-violet-400 bg-violet-500/5 hover:bg-violet-500/10 transition-colors"
            >
              <Microscope size={10} />
              Planejar pesquisa
            </button>
          </>
        )}

        {etapa === "planejando" && (
          <div className="flex items-center gap-2 text-xs text-violet-400">
            <Loader2 size={11} className="animate-spin" />
            Analisando os autos e gerando plano investigativo… (~5s)
          </div>
        )}

        {etapa === "revisando" && (
          <div className="space-y-2">
            <p className="text-xs text-zinc-400 font-semibold">
              Plano investigativo para <span className="text-violet-300">{nomePessoa}</span>
              <span className="text-zinc-600 font-normal"> — revise e edite antes de executar:</span>
            </p>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-xs text-zinc-200 font-mono leading-relaxed focus:outline-none focus:ring-1 focus:ring-violet-500 resize-y"
              rows={10}
              value={briefing}
              onChange={e => setBriefing(e.target.value)}
            />
            <p className="text-xs text-zinc-600">
              Custo estimado: <span className="text-amber-400">US$ 1–3</span>. O relatório pode levar 5–15 min.
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleExecutar}
                disabled={!briefing.trim()}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-700 text-white font-medium transition-colors disabled:opacity-50"
              >
                <Microscope size={10} />
                Executar pesquisa
              </button>
              <button
                onClick={() => setEtapa("idle")}
                className="text-xs px-3 py-1.5 rounded border border-zinc-700 text-zinc-400 hover:border-zinc-600 transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        {etapa === "iniciado" && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-xs text-violet-400">
              <Loader2 size={11} className="animate-spin" />
              Pesquisa em andamento… (5–15 min)
            </div>
            <p className="text-xs text-zinc-600">
              O documento aparecerá em <span className="text-zinc-400">Documentos IA</span> com borda âmbar ao concluir.
            </p>
          </div>
        )}

        {etapa === "concluido" && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-violet-400 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-400 inline-block" />
              Relatório disponível
            </span>
            <button
              className="text-xs text-violet-400 underline hover:text-violet-300 cursor-pointer"
              onClick={() => {
                if (onVerRelatorio) {
                  onVerRelatorio();
                } else {
                  document.getElementById("documentos-ia")?.scrollIntoView({ behavior: "smooth" });
                }
              }}
            >
              Ver relatório ↓
            </button>
          </div>
        )}

        {etapa === "erro" && (
          <button
            onClick={() => { setEtapa("idle"); setErroMsg(null); }}
            className="text-xs text-zinc-500 hover:text-zinc-300 underline"
          >
            Tentar novamente
          </button>
        )}
      </div>
    </div>
  );
}

// ── Card de Personagem ────────────────────────────────────────────────────────

function CardPersonagem({
  p, inqueritoId, modulos, onToggleModulo, resultado, executando, onVerRelatorio,
}: {
  p: PersonagemAnalise;
  inqueritoId: string;
  modulos: string[];
  onToggleModulo: (modId: string) => void;
  resultado: any;
  executando: boolean;
  onVerRelatorio?: () => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const [execIndividual, setExecIndividual] = useState(false);
  const [resIndividual, setResIndividual] = useState<any>(resultado);
  const [confirmando, setConfirmando] = useState(false);

  const custo = modulos.reduce((sum, m) => sum + (OSINT_MODULOS.find(x => x.id === m)?.custo || 0), 0);
  const temCross = p.historico_inqueritos?.length > 0;
  const statusFinal = resIndividual || resultado;

  const doExecutar = async () => {
    setConfirmando(false);
    setExecIndividual(true);
    try {
      const res = await osintLote(inqueritoId, [{ pessoa_id: p.pessoa_id, modulos }]);
      const r = res.resultados?.find((x: any) => x.pessoa_id === p.pessoa_id);
      if (r) setResIndividual(r);
    } catch { /* silencioso */ } finally { setExecIndividual(false); }
  };

  return (
    <div className={`border rounded-xl overflow-hidden transition-colors ${
      expandido ? "border-zinc-700 bg-zinc-900/60" : "border-zinc-800 bg-zinc-900/30 hover:border-zinc-700"
    }`}>
      {/* ── Cabeçalho do card ── */}
      <button
        onClick={() => setExpandido(e => !e)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        <span className="text-zinc-500 shrink-0">
          {expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>

        {/* Ícone tipo */}
        <div className={`p-1.5 rounded border shrink-0 ${
          p.tipo_pessoa === "investigado" ? "bg-red-500/10 border-red-700/30 text-red-400"
          : p.tipo_pessoa === "vitima" ? "bg-blue-500/10 border-blue-700/30 text-blue-400"
          : "bg-zinc-900 border-zinc-700 text-zinc-400"
        }`}>
          {p.cnpj ? <Building size={13} /> : <User size={13} />}
        </div>

        {/* Nome + identificador */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200 truncate">{p.nome}</p>
          <p className={`text-xs mt-0.5 font-mono ${p.cpf || p.cnpj ? "text-zinc-400" : "text-zinc-500 italic"}`}>
            {p.cpf || p.cnpj || "Sem CPF/CNPJ nos autos"}
          </p>
        </div>

        {/* Badges de dados */}
        <div className="hidden sm:flex items-center gap-1 shrink-0">
          <DadosBadge campo={p.dados_nos_autos.cpf}     label="CPF" />
          <DadosBadge campo={p.dados_nos_autos.telefone} label="Tel" />
          <DadosBadge campo={p.dados_nos_autos.endereco} label="End" />
        </div>

        {/* Tipo da pessoa */}
        <TipoPessoa tipo={p.tipo_pessoa} />

        {/* Cross-inquérito */}
        {temCross && (
          <span className="shrink-0 text-xs px-2 py-0.5 rounded border border-orange-700/40 text-orange-400 bg-orange-500/5">
            ⚠ {p.historico_inqueritos.length} IP(s)
          </span>
        )}

        {/* Status OSINT */}
        {execIndividual || executando ? (
          <Loader2 size={14} className="animate-spin text-blue-400 shrink-0" />
        ) : statusFinal?.status === "concluido" ? (
          <CheckCircle size={14} className="text-green-400 shrink-0" />
        ) : statusFinal?.status === "ignorado" ? (
          <MinusCircle size={14} className="text-zinc-600 shrink-0" />
        ) : statusFinal?.status === "erro" ? (
          <XCircle size={14} className="text-red-400 shrink-0" />
        ) : null}
      </button>

      {/* ── Conteúdo expandido ── */}
      {expandido && (
        <div className="border-t border-zinc-800 px-4 py-4 space-y-4">

          {/* Justificativa */}
          {p.justificativa && (
            <p className="text-xs text-zinc-500 italic leading-relaxed">
              "{p.justificativa}"
            </p>
          )}

          {/* Dados públicos gratuitos — Receita Federal / CGU (roda ANTES do pago) */}
          <OsintGratuitoPanel inqueritoId={inqueritoId} pessoaId={p.pessoa_id} />

          {/* Análise preliminar automática (Gemini Flash — gratuita) */}
          <AnalisePreliminarPanel inqueritoId={inqueritoId} pessoaId={p.pessoa_id} />

          {/* OSINT fontes abertas (Serper.dev — sob demanda) */}
          <OsintWebPanel inqueritoId={inqueritoId} pessoaId={p.pessoa_id} />

          {/* OSINT Aprofundado (Gemini Deep Research — sob demanda com confirmação) */}
          <OsintDeepPanel inqueritoId={inqueritoId} pessoaId={p.pessoa_id} nomePessoa={p.nome} onVerRelatorio={onVerRelatorio} />

          {/* Cross-inquérito com links + tooltip de síntese */}
          {temCross && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-orange-400 font-medium">Aparece em:</span>
              {p.historico_inqueritos.map((h) => (
                <div key={h.inquerito_id} className="relative group/tip">
                  <Link
                    href={`/inqueritos/${h.inquerito_id}`}
                    className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border border-orange-700/30 text-orange-300 bg-orange-500/5 hover:border-orange-500/50 hover:text-orange-200 transition-colors"
                  >
                    IP {h.numero}
                    <span className="text-orange-500/60">({h.tipo_pessoa})</span>
                    <ExternalLink size={9} />
                  </Link>
                  {/* Tooltip síntese investigativa */}
                  <div className="invisible group-hover/tip:visible opacity-0 group-hover/tip:opacity-100 transition-all duration-150 absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 w-56 pointer-events-none">
                    <div className="bg-zinc-800 border border-zinc-700 rounded-lg p-3 shadow-2xl">
                      <div className="flex items-baseline gap-1.5 mb-1.5">
                        <span className="font-semibold text-zinc-100 text-xs">IP {h.numero}</span>
                        {h.ano && <span className="text-zinc-600 text-xs">/{h.ano}</span>}
                      </div>
                      <span className={`text-xs uppercase font-bold px-1.5 py-0.5 rounded border inline-block mb-2 ${
                        h.tipo_pessoa === "investigado" ? "border-red-700/40 text-red-400 bg-red-500/5"
                        : h.tipo_pessoa === "vitima" ? "border-blue-700/40 text-blue-400 bg-blue-500/5"
                        : h.tipo_pessoa === "testemunha" ? "border-yellow-700/40 text-yellow-400 bg-yellow-500/5"
                        : "border-zinc-700 text-zinc-500"
                      }`}>{h.tipo_pessoa}</span>
                      {h.descricao ? (
                        <p className="text-zinc-400 text-xs leading-relaxed">{h.descricao}</p>
                      ) : (
                        <p className="text-zinc-600 text-xs italic">Sem descrição disponível.</p>
                      )}
                    </div>
                    <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-[5px] border-r-[5px] border-t-[5px] border-l-transparent border-r-transparent border-t-zinc-700" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Módulos OSINT */}
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Módulos OSINT</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
              {OSINT_MODULOS.map(mod => {
                const ativo = modulos.includes(mod.id);
                return (
                  <label key={mod.id} className="flex items-center gap-2 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={ativo}
                      onChange={() => onToggleModulo(mod.id)}
                      className="w-3 h-3 cursor-pointer accent-blue-500 rounded-sm"
                    />
                    <span className={`text-xs truncate ${ativo ? mod.color : "text-zinc-600"} group-hover:text-zinc-400`}>
                      {mod.label}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Rodapé: custo + botão */}
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-zinc-500">
              {modulos.length > 0
                ? <>Custo estimado: <span className="text-zinc-300 font-mono">R$ {custo.toFixed(2)}</span></>
                : <span className="text-zinc-700">Nenhum módulo selecionado</span>}
            </span>
            <Button
              onClick={() => modulos.length > 0 && setConfirmando(true)}
              disabled={modulos.length === 0 || execIndividual}
              size="sm"
              className="bg-blue-600 hover:bg-blue-700 h-7 text-xs gap-1.5"
            >
              {execIndividual
                ? <><Loader2 size={12} className="animate-spin" /> Consultando...</>
                : <><Play size={11} /> Executar OSINT</>}
            </Button>
          </div>

          {/* Modal de confirmação individual */}
          {confirmando && (
            <ModalConfirmacaoOSINT
              nomePessoa={p.nome}
              modulosSelecionados={modulos
                .map(id => OSINT_MODULOS.find(m => m.id === id))
                .filter(Boolean) as { label: string; custo: number }[]}
              custo={custo}
              onConfirm={doExecutar}
              onCancel={() => setConfirmando(false)}
            />
          )}

          {/* Resultado inline */}
          {statusFinal?.status === "concluido" && statusFinal?.dados && (
            <div className="border-t border-zinc-800 pt-3 space-y-1.5">
              <p className="text-xs text-zinc-500 uppercase tracking-wider">Resultado</p>
              <div className="flex flex-wrap gap-1">
                {statusFinal.dados.apis_executadas?.map((a: string) => (
                  <Badge key={a} variant="outline" className="text-xs border-green-700/30 text-green-400">{a}</Badge>
                ))}
              </div>
              {statusFinal.dados.cadastro?.nome && (
                <p className="text-xs text-zinc-300">{statusFinal.dados.cadastro.nome}</p>
              )}
              {statusFinal.dados.mandados_prisao?.possuiMandado !== undefined && (
                <p className={`text-xs ${statusFinal.dados.mandados_prisao.possuiMandado ? "text-red-400" : "text-green-400"}`}>
                  {statusFinal.dados.mandados_prisao.possuiMandado ? "⚠ Mandado de prisão ativo" : "✓ Sem mandados"}
                </p>
              )}
            </div>
          )}
          {statusFinal?.status === "erro" && (
            <div className="border-t border-zinc-800 pt-3 text-xs text-red-400 flex gap-2">
              <AlertTriangle size={12} className="shrink-0 mt-0.5" /> {statusFinal.mensagem || "Erro na consulta"}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Painel principal ──────────────────────────────────────────────────────────

export function PainelInvestigacao({ inqueritoId, onVerRelatorio }: { inqueritoId: string; onVerRelatorio?: () => void }) {
  const [analise, setAnalise] = useState<any | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [modulos, setModulos] = useState<Record<string, string[]>>({});
  const [resultados, setResultados] = useState<Record<string, any>>({});
  const [executandoLote, setExecutandoLote] = useState(false);
  const [confirmandoLote, setConfirmandoLote] = useState(false);

  useEffect(() => {
    setAnalise(null); setErro(null); setResultados({}); setModulos({});
    setCarregando(true);
    osintSugestao(inqueritoId)
      .then(res => {
        const a = res.analise;
        setAnalise(a);
        const init: Record<string, string[]> = {};
        (a.personagens || []).forEach((p: PersonagemAnalise) => {
          init[p.pessoa_id] = initSugestao(p.perfil_sugerido);
        });
        setModulos(init);
      })
      .catch(e => setErro(e?.response?.data?.detail || "Erro ao analisar personagens."))
      .finally(() => setCarregando(false));
  }, [inqueritoId]);

  // OSINT só para suspeitos e coautores — vítimas, testemunhas e policiais são excluídos
  const PAPEIS_OSINT = new Set(["suspeito_principal", "coautor", "investigado"]);
  const personagens: PersonagemAnalise[] = (analise?.personagens || []).filter(
    (p: PersonagemAnalise) => !p.tipo_pessoa || PAPEIS_OSINT.has(p.tipo_pessoa)
  );

  const toggleModulo = (pessoaId: string, moduloId: string) => {
    setModulos(prev => {
      const atuais = prev[pessoaId] || [];
      return {
        ...prev,
        [pessoaId]: atuais.includes(moduloId)
          ? atuais.filter(m => m !== moduloId)
          : [...atuais, moduloId],
      };
    });
  };

  const custoTotal = personagens.reduce((acc, p) => {
    return acc + (modulos[p.pessoa_id] || []).reduce((s, m) => s + (OSINT_MODULOS.find(x => x.id === m)?.custo || 0), 0);
  }, 0);

  const doExecutarTodos = async () => {
    setConfirmandoLote(false);
    const itens = personagens
      .filter(p => (modulos[p.pessoa_id] || []).length > 0)
      .map(p => ({ pessoa_id: p.pessoa_id, modulos: modulos[p.pessoa_id] }));
    if (!itens.length) return;
    setExecutandoLote(true);
    try {
      const res = await osintLote(inqueritoId, itens);
      const mapa: Record<string, any> = {};
      (res.resultados || []).forEach((r: any) => { mapa[r.pessoa_id] = r; });
      setResultados(mapa);
    } catch { /* silencioso */ } finally { setExecutandoLote(false); }
  };

  if (carregando) return (
    <div className="flex items-center justify-center h-48 gap-3 text-zinc-400">
      <Loader2 size={20} className="animate-spin text-blue-500" />
      Analisando personagens nos autos...
    </div>
  );

  if (erro) return (
    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex gap-3 text-red-400 text-sm">
      <AlertTriangle size={16} className="shrink-0 mt-0.5" /> {erro}
    </div>
  );

  const totalPersonagens = (analise?.personagens || []).length;
  if (!personagens.length) return (
    <div className="flex flex-col items-center justify-center h-48 text-zinc-500 text-center">
      <UserSearch className="w-12 h-12 mb-3 text-zinc-800" />
      {totalPersonagens > 0
        ? <>
            <p className="text-sm">Nenhum suspeito ou coautor identificado ainda.</p>
            <p className="text-xs mt-1 text-zinc-600">{totalPersonagens} personagem(ns) nos autos (vítimas, testemunhas, policiais) — OSINT não aplicável.</p>
          </>
        : <>
            <p className="text-sm">Nenhum personagem indexado neste inquérito.</p>
            <p className="text-xs mt-1 text-zinc-600">Inicie a ingestão de documentos para detectar pessoas automaticamente.</p>
          </>}
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Header com classificação e ação em lote */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs">
          {analise?.crime_complexo
            ? <Badge variant="outline" className="border-red-700/40 text-red-400 bg-red-500/5">Crime complexo</Badge>
            : <Badge variant="outline" className="border-zinc-700 text-zinc-500">Crime simples</Badge>}
          <span className="text-zinc-600">{personagens.length} suspeito(s)/coautor(es)</span>
        </div>
        <div className="flex items-center gap-3">
          {custoTotal > 0 && (
            <span className="text-xs text-zinc-500">
              Total selecionado: <span className="text-zinc-300 font-mono">R$ {custoTotal.toFixed(2)}</span>
            </span>
          )}
          <Button
            onClick={() => custoTotal > 0 && setConfirmandoLote(true)}
            disabled={executandoLote || custoTotal === 0}
            size="sm"
            className="bg-blue-600 hover:bg-blue-700 h-8 text-xs gap-1.5"
          >
            {executandoLote
              ? <><Loader2 size={12} className="animate-spin" /> Executando...</>
              : <><Play size={11} /> Executar todos</>}
          </Button>
        </div>
      </div>

      {/* Cards de personagens */}
      <div className="space-y-2">
        {personagens.map(p => (
          <CardPersonagem
            key={p.pessoa_id}
            p={p}
            inqueritoId={inqueritoId}
            modulos={modulos[p.pessoa_id] || []}
            onToggleModulo={(modId) => toggleModulo(p.pessoa_id, modId)}
            resultado={resultados[p.pessoa_id]}
            executando={executandoLote}
            onVerRelatorio={onVerRelatorio}
          />
        ))}
      </div>

      {/* Modal de confirmação — executar todos */}
      {confirmandoLote && (() => {
        const todosModulos = personagens.flatMap(p =>
          (modulos[p.pessoa_id] || []).map(id => OSINT_MODULOS.find(m => m.id === id)).filter(Boolean) as { label: string; custo: number }[]
        );
        const nomes = personagens
          .filter(p => (modulos[p.pessoa_id] || []).length > 0)
          .map(p => p.nome)
          .join(", ");
        return (
          <ModalConfirmacaoOSINT
            nomePessoa={`${personagens.filter(p => (modulos[p.pessoa_id] || []).length > 0).length} personagem(ns): ${nomes}`}
            modulosSelecionados={todosModulos}
            custo={custoTotal}
            onConfirm={doExecutarTodos}
            onCancel={() => setConfirmandoLote(false)}
          />
        );
      })()}
    </div>
  );
}
