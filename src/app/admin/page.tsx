"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DollarSign, Zap, BarChart2, RefreshCw, AlertTriangle, CheckCircle,
  Pencil, Check, X, Settings, Globe, Database, Server, Search, Bot,
} from "lucide-react";
import {
  getConsumoSaldo, getConsumoRanking, getConsumoHistorico, getConsumoModelos,
  getConsumoExternos, salvarCustoExterno, getConsumoConfig, salvarConsumoConfig,
} from "@/lib/api";

// ── Constantes ────────────────────────────────────────────────────────────────

const TIER_COLOR: Record<string, string> = {
  premium:  "bg-purple-500/20 text-purple-300 border-purple-500/30",
  standard: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  triagem:  "bg-green-500/20 text-green-300 border-green-500/30",
  extracao: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
  resumo:   "bg-orange-500/20 text-orange-300 border-orange-500/30",
  auditoria:"bg-red-500/20 text-red-300 border-red-500/30",
  vision:   "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  economico:"bg-zinc-500/20 text-zinc-300 border-zinc-500/30",
};

const SERVICOS_CONFIG: Record<string, { label: string; icon: React.ReactNode; cor: string }> = {
  vercel:        { label: "Vercel",         icon: <Globe size={14} />,    cor: "text-white" },
  railway:       { label: "Railway",        icon: <Server size={14} />,   cor: "text-purple-400" },
  supabase:      { label: "Supabase",       icon: <Database size={14} />, cor: "text-emerald-400" },
  serper:        { label: "Serper.dev",     icon: <Search size={14} />,   cor: "text-sky-400" },
  gemini_studio: { label: "Gemini Studio",  icon: <Bot size={14} />,      cor: "text-amber-400" },
  outro:         { label: "Outro",          icon: <DollarSign size={14}/>, cor: "text-zinc-400" },
};

function pct(value: number, total: number) {
  if (!total) return 0;
  return Math.min(100, (value / total) * 100);
}

// ── Componente de edição inline ───────────────────────────────────────────────

function CustoExternoCard({
  servico,
  valor,
  observacao,
  onSalvar,
}: {
  servico: string;
  valor: number;
  observacao?: string;
  onSalvar: (usd: number, brl: number, obs: string) => Promise<void>;
}) {
  const [editando, setEditando] = useState(false);
  const [usd, setUsd] = useState(String(valor || ""));
  const [cotacao, setCotacao] = useState("5.80");
  const [obs, setObs] = useState(observacao || "");
  const [salvando, setSalvando] = useState(false);

  const brl = parseFloat(usd || "0") * parseFloat(cotacao || "1");
  const cfg = SERVICOS_CONFIG[servico] || SERVICOS_CONFIG.outro;

  const handleSalvar = async () => {
    setSalvando(true);
    try {
      await onSalvar(parseFloat(usd || "0"), brl, obs);
      setEditando(false);
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="flex items-center justify-between py-2.5 border-b border-zinc-800/60 last:border-0">
      <div className="flex items-center gap-2.5 min-w-0">
        <span className={`shrink-0 ${cfg.cor}`}>{cfg.icon}</span>
        <span className="text-sm text-zinc-300 font-medium">{cfg.label}</span>
        {observacao && !editando && (
          <span className="text-xs text-zinc-600 truncate max-w-[120px]" title={observacao}>{observacao}</span>
        )}
      </div>

      {editando ? (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <span className="text-xs text-zinc-500">US$</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={usd}
              onChange={e => setUsd(e.target.value)}
              className="w-20 text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-100 focus:outline-none focus:border-blue-500"
              placeholder="0.00"
            />
          </div>
          <div className="flex items-center gap-1">
            <span className="text-xs text-zinc-500">×</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={cotacao}
              onChange={e => setCotacao(e.target.value)}
              className="w-16 text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-100 focus:outline-none focus:border-blue-500"
              title="Cotação USD→BRL"
            />
            <span className="text-xs text-zinc-500">= R$ {brl.toFixed(2)}</span>
          </div>
          <input
            value={obs}
            onChange={e => setObs(e.target.value)}
            placeholder="obs..."
            className="w-24 text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-400 focus:outline-none"
          />
          <button onClick={handleSalvar} disabled={salvando} className="text-green-400 hover:text-green-300 disabled:opacity-50">
            <Check size={14} />
          </button>
          <button onClick={() => setEditando(false)} className="text-zinc-500 hover:text-zinc-300">
            <X size={14} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-white">
            {valor > 0 ? `R$ ${valor.toFixed(2)}` : <span className="text-zinc-600 text-xs">não informado</span>}
          </span>
          <button onClick={() => setEditando(true)} className="text-zinc-600 hover:text-zinc-400 transition-colors">
            <Pencil size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function AdminPage() {
  const [saldo, setSaldo]       = useState<any>(null);
  const [ranking, setRanking]   = useState<any[]>([]);
  const [historico, setHistorico] = useState<any[]>([]);
  const [modelos, setModelos]   = useState<any[]>([]);
  const [externos, setExternos] = useState<any>(null);
  const [config, setConfig]     = useState<any>(null);
  const [loading, setLoading]   = useState(true);

  // Editor de config
  const [editandoConfig, setEditandoConfig] = useState(false);
  const [cfgBudget, setCfgBudget]           = useState("");
  const [cfgAlerta, setCfgAlerta]           = useState("");
  const [cfgCotacao, setCfgCotacao]         = useState("");
  const [salvandoConfig, setSalvandoConfig] = useState(false);

  async function carregar() {
    setLoading(true);
    try {
      const [s, r, h, m, e, c] = await Promise.all([
        getConsumoSaldo(),
        getConsumoRanking(),
        getConsumoHistorico(30),
        getConsumoModelos(),
        getConsumoExternos(),
        getConsumoConfig(),
      ]);
      setSaldo(s);
      setRanking(r);
      setHistorico(h);
      setModelos(m);
      setExternos(e);
      setConfig(c);
      setCfgBudget(String(c.budget_brl));
      setCfgAlerta(String(c.budget_alert_brl));
      setCfgCotacao(String(c.cotacao_dolar));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { carregar(); }, []);

  const handleSalvarCustoExterno = async (servico: string) => {
    return async (usd: number, brl: number, obs: string) => {
      await salvarCustoExterno(servico, usd, brl, obs || undefined);
      const e = await getConsumoExternos();
      setExternos(e);
    };
  };

  const handleSalvarConfig = async () => {
    setSalvandoConfig(true);
    try {
      const res = await salvarConsumoConfig(
        parseFloat(cfgBudget),
        parseFloat(cfgAlerta),
        parseFloat(cfgCotacao),
      );
      setConfig({ budget_brl: res.budget_brl, budget_alert_brl: res.budget_alert_brl, cotacao_dolar: res.cotacao_dolar });
      setEditandoConfig(false);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Erro ao salvar configuração.");
    } finally {
      setSalvandoConfig(false);
    }
  };

  const maxGastoAgente = Math.max(...ranking.map(r => r.gasto_brl), 0.001);
  const maxGastoModelo = Math.max(...modelos.map(m => m.gasto_brl), 0.001);
  const maxHistorico   = Math.max(...historico.map(h => h.gasto_brl), 0.001);

  // Monta mapa de custos externos por serviço
  const custosPorServico: Record<string, { custo_brl: number; observacao?: string }> = {};
  if (externos?.externos) {
    for (const e of externos.externos) {
      custosPorServico[e.servico] = { custo_brl: e.custo_brl, observacao: e.observacao };
    }
  }

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Administrativo</h1>
          <p className="text-zinc-400 mt-1">Consumo de API e orçamento — mês corrente</p>
        </div>
        <button
          onClick={carregar}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm text-zinc-300 transition-colors"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Atualizar
        </button>
      </div>

      {loading && !saldo ? (
        <div className="text-zinc-500">Carregando dados...</div>
      ) : saldo ? (
        <>
          {/* ── Cards de saldo Gemini ─────────────────────────────────────── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-xs font-medium text-zinc-400">Gemini — Mês</CardTitle>
                <DollarSign size={14} className="text-zinc-500" />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold text-white">R$ {saldo.gasto_brl.toFixed(2)}</p>
                <p className="text-xs text-zinc-500 mt-1">de R$ {saldo.budget_brl.toFixed(0)} limite</p>
              </CardContent>
            </Card>

            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-xs font-medium text-zinc-400">Saldo Disponível</CardTitle>
                {saldo.alerta_ativo
                  ? <AlertTriangle size={14} className="text-yellow-400" />
                  : <CheckCircle size={14} className="text-green-400" />}
              </CardHeader>
              <CardContent>
                <p className={`text-2xl font-bold ${saldo.alerta_ativo ? "text-yellow-400" : "text-green-400"}`}>
                  R$ {saldo.saldo_brl.toFixed(2)}
                </p>
                <p className="text-xs text-zinc-500 mt-1">{saldo.percentual_usado.toFixed(1)}% usado</p>
              </CardContent>
            </Card>

            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-xs font-medium text-zinc-400">Tokens Consumidos</CardTitle>
                <Zap size={14} className="text-zinc-500" />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold text-white">
                  {saldo.tokens_total >= 1_000_000
                    ? `${(saldo.tokens_total / 1_000_000).toFixed(1)}M`
                    : `${(saldo.tokens_total / 1_000).toFixed(0)}k`}
                </p>
                <p className="text-xs text-zinc-500 mt-1">{saldo.chamadas_total} chamadas</p>
              </CardContent>
            </Card>

            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-xs font-medium text-zinc-400">Total Consolidado</CardTitle>
                <BarChart2 size={14} className="text-zinc-500" />
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold text-amber-400">
                  R$ {externos ? externos.total_consolidado_brl.toFixed(2) : saldo.gasto_brl.toFixed(2)}
                </p>
                <p className="text-xs text-zinc-500 mt-1">Gemini + serviços externos</p>
              </CardContent>
            </Card>
          </div>

          {/* ── Custos por Serviço Externo ────────────────────────────────── */}
          {externos && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold">Custos por Serviço — {externos.mes}</CardTitle>
                <span className="text-xs text-zinc-500">clique em ✏️ para editar</span>
              </CardHeader>
              <CardContent className="space-y-0 divide-y divide-zinc-800/0">
                {/* Gemini — automático */}
                <div className="flex items-center justify-between py-2.5 border-b border-zinc-800/60">
                  <div className="flex items-center gap-2.5">
                    <span className="text-amber-400"><Bot size={14} /></span>
                    <span className="text-sm text-zinc-300 font-medium">Gemini API</span>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 border-amber-700/30 text-amber-500">auto</Badge>
                  </div>
                  <span className="text-sm font-semibold text-white">R$ {externos.gemini_brl.toFixed(2)}</span>
                </div>

                {/* Serviços manuais */}
                {Object.keys(SERVICOS_CONFIG).filter(s => s !== "gemini_studio").map(servico => (
                  <CustoExternoCard
                    key={servico}
                    servico={servico}
                    valor={custosPorServico[servico]?.custo_brl || 0}
                    observacao={custosPorServico[servico]?.observacao}
                    onSalvar={handleSalvarCustoExterno(servico)}
                  />
                ))}

                {/* Total */}
                <div className="flex items-center justify-between pt-3 mt-1">
                  <span className="text-sm font-bold text-zinc-300">Total do Mês</span>
                  <span className="text-lg font-bold text-amber-400">R$ {externos.total_consolidado_brl.toFixed(2)}</span>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Ranking por agente */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">Gasto por Agente (Gemini)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {ranking.length === 0 ? (
                  <p className="text-zinc-500 text-sm">Nenhum registro ainda.</p>
                ) : (
                  ranking.map((r, i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className="text-zinc-200 font-medium">{r.agente}</span>
                          <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${TIER_COLOR[r.tier] ?? "bg-zinc-800 text-zinc-400"}`}>
                            {r.tier}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 text-zinc-400 text-xs">
                          <span>{r.chamadas}x</span>
                          <span className="text-white font-medium">R$ {r.gasto_brl.toFixed(4)}</span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct(r.gasto_brl, maxGastoAgente)}%` }} />
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Ranking por modelo */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">Gasto por Modelo</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {modelos.length === 0 ? (
                  <p className="text-zinc-500 text-sm">Nenhum registro ainda.</p>
                ) : (
                  modelos.map((m, i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-zinc-200 font-medium truncate max-w-[180px]" title={m.modelo}>{m.modelo}</span>
                        <div className="flex items-center gap-3 text-zinc-400 text-xs">
                          <span>{(m.tokens_total / 1000).toFixed(0)}k tok</span>
                          <span className="text-white font-medium">R$ {m.gasto_brl.toFixed(4)}</span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full bg-purple-500 rounded-full" style={{ width: `${pct(m.gasto_brl, maxGastoModelo)}%` }} />
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          {/* Histórico diário */}
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Histórico Diário — Gemini (30 dias)</CardTitle>
            </CardHeader>
            <CardContent>
              {historico.length === 0 ? (
                <p className="text-zinc-500 text-sm">Nenhum registro ainda.</p>
              ) : (
                <div className="flex items-end gap-1 h-24">
                  {historico.map((h, i) => (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                      <div
                        className="w-full bg-blue-500/70 hover:bg-blue-400 rounded-sm transition-colors cursor-default"
                        style={{ height: `${Math.max(4, pct(h.gasto_brl, maxHistorico) * 0.88)}px` }}
                        title={`${h.dia}: R$ ${h.gasto_brl.toFixed(4)} (${h.chamadas} chamadas)`}
                      />
                      {i % 7 === 0 && (
                        <span className="text-[9px] text-zinc-600 rotate-45 origin-left absolute -bottom-5 left-0">
                          {h.dia.slice(5)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Configurações de orçamento */}
          {config && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Settings size={14} className="text-zinc-500" />
                  <CardTitle className="text-sm font-semibold">Configurações de Orçamento</CardTitle>
                </div>
                {!editandoConfig && (
                  <button onClick={() => setEditandoConfig(true)} className="text-zinc-600 hover:text-zinc-400 transition-colors">
                    <Pencil size={13} />
                  </button>
                )}
              </CardHeader>
              <CardContent>
                {editandoConfig ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <label className="text-xs text-zinc-500 mb-1 block">Limite Mensal (R$)</label>
                        <input
                          type="number" min="0" step="10"
                          value={cfgBudget} onChange={e => setCfgBudget(e.target.value)}
                          className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-100 focus:outline-none focus:border-blue-500"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-zinc-500 mb-1 block">Alerta em (R$)</label>
                        <input
                          type="number" min="0" step="10"
                          value={cfgAlerta} onChange={e => setCfgAlerta(e.target.value)}
                          className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-100 focus:outline-none focus:border-blue-500"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-zinc-500 mb-1 block">Cotação USD→BRL</label>
                        <input
                          type="number" min="0" step="0.01"
                          value={cfgCotacao} onChange={e => setCfgCotacao(e.target.value)}
                          className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-100 focus:outline-none focus:border-blue-500"
                        />
                      </div>
                    </div>
                    <p className="text-[11px] text-zinc-600">
                      ⚠ Ativo até o próximo restart do Railway. Para persistir, atualize as variáveis de ambiente no Railway.
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={handleSalvarConfig}
                        disabled={salvandoConfig}
                        className="px-4 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50 transition-colors"
                      >
                        {salvandoConfig ? "Salvando..." : "Salvar"}
                      </button>
                      <button
                        onClick={() => setEditandoConfig(false)}
                        className="px-4 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded transition-colors"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-3 gap-6 text-sm">
                    <div>
                      <p className="text-zinc-500 text-xs mb-1">Limite Mensal</p>
                      <p className="text-white font-semibold">R$ {config.budget_brl.toFixed(0)}</p>
                    </div>
                    <div>
                      <p className="text-zinc-500 text-xs mb-1">Alerta em</p>
                      <p className="text-yellow-400 font-semibold">R$ {config.budget_alert_brl.toFixed(0)}</p>
                    </div>
                    <div>
                      <p className="text-zinc-500 text-xs mb-1">Cotação USD</p>
                      <p className="text-zinc-300 font-semibold">R$ {config.cotacao_dolar.toFixed(2)}</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        <div className="text-zinc-500">Erro ao carregar dados. Verifique se o backend está online.</div>
      )}
    </div>
  );
}
