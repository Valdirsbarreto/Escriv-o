"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BiometricSetup } from "@/components/BiometricSetup";
import { Badge } from "@/components/ui/badge";
import {
  DollarSign, Zap, BarChart2, RefreshCw, AlertTriangle, CheckCircle,
  Pencil, Check, X, Settings, Globe, Database, Server, Search, Bot, TrendingUp, Microscope,
} from "lucide-react";
import {
  getConsumoSaldo, getConsumoRanking, getConsumoHistorico, getConsumoModelos,
  getConsumoExternos, salvarCustoExterno, getConsumoConfig, salvarConsumoConfig,
  getConsumoOsintPorInquerito, getConsumoProjecao, coletarBillingAgora, getSupabaseUsage, getBillingStatus,
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
  serper:        { label: "Serper.dev",       icon: <Search size={14} />,     cor: "text-sky-400" },
  gemini_studio: { label: "Gemini Studio",    icon: <Bot size={14} />,        cor: "text-amber-400" },
  deep_research: { label: "Deep Research",    icon: <Microscope size={14} />, cor: "text-violet-400" },
  direct_data:   { label: "direct.data",      icon: <Database size={14} />,   cor: "text-blue-400" },
  outro:         { label: "Outro",            icon: <DollarSign size={14} />, cor: "text-zinc-400" },
};

function pct(value: number, total: number) {
  if (!total) return 0;
  return Math.min(100, (value / total) * 100);
}

// ── Componente de edição inline ───────────────────────────────────────────────

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  official_api:        { label: "auto",     cls: "border-emerald-700/30 text-emerald-400" },
  estimated:           { label: "estimado", cls: "border-yellow-700/30 text-yellow-500" },
  internal_telemetry:  { label: "auto",     cls: "border-sky-700/30 text-sky-400" },
  manual:              { label: "manual",   cls: "border-zinc-700/30 text-zinc-500" },
};

function CustoExternoCard({
  servico,
  valor,
  observacao,
  source,
  onSalvar,
}: {
  servico: string;
  valor: number;
  observacao?: string;
  source?: string;
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
        {source && SOURCE_BADGE[source] && !editando && (
          <Badge variant="outline" className={`text-xs px-1.5 py-0 ${SOURCE_BADGE[source].cls}`}>
            {SOURCE_BADGE[source].label}
          </Badge>
        )}
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
            {(valor > 0 || source) ? `R$ ${valor.toFixed(2)}` : <span className="text-zinc-600 text-xs">não informado</span>}
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

// Gera lista de meses disponíveis (últimos 6)
function mesesDisponiveis(): { value: string; label: string }[] {
  const meses = [];
  const agora = new Date();
  for (let i = 0; i < 6; i++) {
    const d = new Date(agora.getFullYear(), agora.getMonth() - i, 1);
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleString("pt-BR", { month: "long", year: "numeric" });
    meses.push({ value, label });
  }
  return meses;
}

export default function AdminPage() {
  const [mesSelecionado, setMesSelecionado] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [saldo, setSaldo]       = useState<any>(null);
  const [ranking, setRanking]   = useState<any[]>([]);
  const [historico, setHistorico] = useState<any[]>([]);
  const [modelos, setModelos]   = useState<any[]>([]);
  const [externos, setExternos] = useState<any>(null);
  const [config, setConfig]     = useState<any>(null);
  const [osintInqueritos, setOsintInqueritos] = useState<any[]>([]);
  const [projecao, setProjecao] = useState<any>(null);
  const [supabaseUsage, setSupabaseUsage] = useState<any>(null);
  const [loading, setLoading]   = useState(true);
  const [coletando, setColetando] = useState(false);
  const [coletaMsg, setColetaMsg] = useState<string | null>(null);

  // Editor de config
  const [editandoConfig, setEditandoConfig] = useState(false);
  const [cfgBudget, setCfgBudget]           = useState("");
  const [cfgAlerta, setCfgAlerta]           = useState("");
  const [cfgCotacao, setCfgCotacao]         = useState("");
  const [salvandoConfig, setSalvandoConfig] = useState(false);

  async function carregar(mes?: string) {
    setLoading(true);
    const mesRef = mes || mesSelecionado;
    try {
      const [s, r, h, m, e, c, o, p, su] = await Promise.all([
        getConsumoSaldo(),
        getConsumoRanking(),
        getConsumoHistorico(30),
        getConsumoModelos(),
        getConsumoExternos(mesRef),
        getConsumoConfig(),
        getConsumoOsintPorInquerito(),
        getConsumoProjecao(),
        getSupabaseUsage().catch(() => null),
      ]);
      setSaldo(s);
      setRanking(r);
      setHistorico(h);
      setModelos(m);
      setExternos(e);
      setConfig(c);
      setOsintInqueritos(o);
      setProjecao(p);
      setSupabaseUsage(su);
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

  const handleMesChange = (mes: string) => {
    setMesSelecionado(mes);
    carregar(mes);
  };

  const handleSalvarCustoExterno = (servico: string) => {
    return async (usd: number, brl: number, obs: string) => {
      await salvarCustoExterno(servico, usd, brl, obs || undefined, mesSelecionado);
      const e = await getConsumoExternos(mesSelecionado);
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

  const handleColetar = async () => {
    setColetando(true);
    setColetaMsg("Disparando coleta...");
    try {
      const res = await coletarBillingAgora();
      const taskId: string = res.task_id;
      setColetaMsg(`⏳ Coletando Vercel · Railway · Supabase · Serper…`);

      let tentativas = 0;
      const poll = setInterval(async () => {
        tentativas++;
        try {
          const s = await getBillingStatus(taskId);
          if (s.status === "SUCCESS") {
            clearInterval(poll);
            setColetaMsg("✅ Coleta concluída! Atualizando dados...");
            setColetando(false);
            setTimeout(() => { carregar(); setColetaMsg(null); }, 1500);
          } else if (s.status === "FAILURE") {
            clearInterval(poll);
            setColetaMsg(`❌ Falha na coleta: ${s.error ?? "erro desconhecido"}`);
            setColetando(false);
          } else if (tentativas >= 40) {
            // 40 × 3s = 2 min máximo
            clearInterval(poll);
            setColetaMsg("⚠️ Coleta demorou mais que o esperado. Tente Atualizar manualmente.");
            setColetando(false);
          } else {
            const statusLabel: Record<string, string> = {
              PENDING: "aguardando worker…",
              STARTED: "em andamento…",
              RETRY:   "tentando novamente…",
            };
            setColetaMsg(`⏳ ${statusLabel[s.status] ?? s.status} (${tentativas * 3}s)`);
          }
        } catch {
          // falha no poll — continua tentando
        }
      }, 3000);
    } catch {
      setColetaMsg("❌ Erro ao disparar coleta. Verifique o backend.");
      setColetando(false);
    }
  };

  const maxGastoAgente = Math.max(...ranking.map(r => r.gasto_brl), 0.001);
  const maxGastoModelo = Math.max(...modelos.map(m => m.gasto_brl), 0.001);
  const maxHistorico   = Math.max(...historico.map(h => h.gasto_brl), 0.001);

  // Monta mapa de custos externos por serviço
  const custosPorServico: Record<string, { custo_brl: number; observacao?: string; source?: string }> = {};
  if (externos?.externos) {
    for (const e of externos.externos) {
      custosPorServico[e.servico] = { custo_brl: e.custo_brl, observacao: e.observacao, source: e.source };
    }
  }

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      {/* Segurança do dispositivo */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-3">Segurança</h2>
        <BiometricSetup />
      </div>

      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Administrativo</h1>
          <p className="text-zinc-400 mt-1">Consumo de API e orçamento</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={mesSelecionado}
            onChange={e => handleMesChange(e.target.value)}
            className="text-sm bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-300 focus:outline-none focus:border-blue-500"
          >
            {mesesDisponiveis().map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <button
            onClick={handleColetar}
            disabled={coletando}
            title="Dispara a coleta automática de custos externos (Vercel, Railway, Supabase, Serper)"
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm text-zinc-400 transition-colors disabled:opacity-50"
          >
            <DollarSign size={14} className={coletando ? "animate-pulse text-emerald-400" : ""} />
            {coletando ? "Coletando..." : "Coletar Agora"}
          </button>
          <button
            onClick={() => carregar()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm text-zinc-300 transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Atualizar
          </button>
        </div>
      </div>

      {coletaMsg && (
        <div className={`text-xs rounded-lg px-4 py-2 ${
          coletaMsg.startsWith("❌")
            ? "text-red-400 bg-red-950/30 border border-red-800/40"
            : coletaMsg.startsWith("⚠️")
            ? "text-yellow-400 bg-yellow-950/30 border border-yellow-800/40"
            : "text-emerald-400 bg-emerald-950/30 border border-emerald-800/40"
        }`}>
          {coletaMsg}
        </div>
      )}

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

          {/* ── Projeção Mensal ───────────────────────────────────────────── */}
          {projecao && (
            <Card className={`border ${projecao.alerta ? "bg-yellow-950/30 border-yellow-800/40" : "bg-zinc-900 border-zinc-800"}`}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div className="flex items-center gap-2">
                  <TrendingUp size={14} className={projecao.alerta ? "text-yellow-400" : "text-zinc-500"} />
                  <CardTitle className="text-sm font-semibold">Projeção para o Fim do Mês</CardTitle>
                </div>
                {projecao.alerta && (
                  <Badge variant="outline" className="text-xs border-yellow-700/40 text-yellow-400">alerta</Badge>
                )}
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-zinc-500 text-xs mb-1">Gasto até hoje</p>
                    <p className="text-white font-semibold">R$ {projecao.gasto_ate_hoje.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-zinc-500 text-xs mb-1">Ritmo diário (7d)</p>
                    <p className="text-zinc-300 font-semibold">R$ {projecao.ritmo_diario_brl.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-zinc-500 text-xs mb-1">Dias restantes</p>
                    <p className="text-zinc-300 font-semibold">{projecao.dias_restantes} dias</p>
                  </div>
                  <div>
                    <p className="text-zinc-500 text-xs mb-1">Projeção fim do mês</p>
                    <p className={`font-bold text-lg ${projecao.alerta ? "text-yellow-400" : "text-green-400"}`}>
                      R$ {projecao.projecao_fim_mes.toFixed(2)}
                    </p>
                    <p className="text-xs text-zinc-500">{projecao.percentual_projetado.toFixed(1)}% do limite</p>
                  </div>
                </div>
                {/* barra de progresso projetado */}
                <div className="mt-3 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${projecao.alerta ? "bg-yellow-400" : "bg-green-500"}`}
                    style={{ width: `${Math.min(100, projecao.percentual_projetado)}%` }}
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* ── Supabase — Uso de Armazenamento ─────────────────────────── */}
          {supabaseUsage && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div className="flex items-center gap-2">
                  <Database size={14} className="text-emerald-400" />
                  <CardTitle className="text-sm font-semibold">Supabase — Armazenamento</CardTitle>
                </div>
                <span className="text-xs text-zinc-500">plano gratuito</span>
              </CardHeader>
              <CardContent className="space-y-4">
                {[
                  { label: "Banco de dados (PostgreSQL)", key: "db",      color: "bg-emerald-500", icon: "🗄️" },
                  { label: "Storage (PDFs / arquivos)",   key: "storage", color: "bg-sky-500",     icon: "📁" },
                  { label: "Egress (transferência)",       key: "egress",  color: "bg-violet-500",  icon: "↗️" },
                ].map(({ label, key, color, icon }) => {
                  const m = supabaseUsage[key];
                  if (!m) return null;
                  const usedStr = m.size_mb >= 1024
                    ? `${(m.size_mb / 1024).toFixed(2)} GB`
                    : `${m.size_mb} MB`;
                  const limStr = m.limit_mb >= 1024
                    ? `${(m.limit_mb / 1024).toFixed(0)} GB`
                    : `${m.limit_mb} MB`;
                  const alert = m.pct >= 80;
                  return (
                    <div key={key} className="space-y-1.5">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-zinc-300 flex items-center gap-1.5">
                          <span className="text-base">{icon}</span>
                          {label}
                          {m.fonte === "indisponivel" && (
                            <span className="text-xs text-zinc-600 ml-1">(API indisponível)</span>
                          )}
                        </span>
                        <span className={`font-semibold text-xs ${alert ? "text-yellow-400" : "text-zinc-300"}`}>
                          {usedStr} / {limStr} ({m.pct}%)
                        </span>
                      </div>
                      <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${alert ? "bg-yellow-400" : color}`}
                          style={{ width: `${Math.max(1, m.pct)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* ── Custos por Serviço Externo ────────────────────────────────── */}
          {externos && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold">Custos por Serviço — {mesSelecionado}</CardTitle>
                <span className="text-xs text-zinc-500">clique em ✏️ para editar</span>
              </CardHeader>
              <CardContent className="space-y-0 divide-y divide-zinc-800/0">
                {/* Gemini — automático */}
                <div className="flex items-center justify-between py-2.5 border-b border-zinc-800/60">
                  <div className="flex items-center gap-2.5">
                    <span className="text-amber-400"><Bot size={14} /></span>
                    <span className="text-sm text-zinc-300 font-medium">Gemini API</span>
                    <Badge variant="outline" className="text-xs px-1.5 py-0 border-amber-700/30 text-amber-500">auto</Badge>
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
                    source={custosPorServico[servico]?.source}
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
                          <Badge variant="outline" className={`text-xs px-1.5 py-0 ${TIER_COLOR[r.tier] ?? "bg-zinc-800 text-zinc-400"}`}>
                            {r.tier}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 text-zinc-400 text-xs">
                          <span>{r.chamadas}x</span>
                          <span className="text-white font-medium">R$ {r.gasto_brl.toFixed(2)}</span>
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
                          <span className="text-white font-medium">R$ {m.gasto_brl.toFixed(2)}</span>
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
                        title={`${h.dia}: R$ ${h.gasto_brl.toFixed(2)} (${h.chamadas} chamadas)`}
                      />
                      {i % 7 === 0 && (
                        <span className="text-xs text-zinc-600 rotate-45 origin-left absolute -bottom-5 left-0">
                          {h.dia.slice(5)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── OSINT por Inquérito ───────────────────────────────────────── */}
          {osintInqueritos.length > 0 && (
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">Custo OSINT por Inquérito (direct.data)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {(() => {
                  const maxOsint = Math.max(...osintInqueritos.map(o => o.custo_brl), 0.001);
                  return osintInqueritos.map((o, i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-zinc-500 font-mono w-5 text-right">{i + 1}.</span>
                          <span className="text-zinc-200 font-medium">{o.numero}</span>
                        </div>
                        <div className="flex items-center gap-3 text-zinc-400 text-xs">
                          <span>{o.total_consultas} consultas</span>
                          <span className="text-white font-medium">R$ {o.custo_brl.toFixed(2)}</span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full bg-sky-500 rounded-full" style={{ width: `${pct(o.custo_brl, maxOsint)}%` }} />
                      </div>
                    </div>
                  ));
                })()}
              </CardContent>
            </Card>
          )}

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
                    <p className="text-xs text-zinc-600">
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
