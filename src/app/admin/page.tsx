"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DollarSign, Zap, BarChart2, RefreshCw, AlertTriangle, CheckCircle,
} from "lucide-react";
import { getConsumoSaldo, getConsumoRanking, getConsumoHistorico, getConsumoModelos } from "@/lib/api";

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

function pct(value: number, total: number) {
  if (!total) return 0;
  return Math.min(100, (value / total) * 100);
}

export default function AdminPage() {
  const [saldo, setSaldo]     = useState<any>(null);
  const [ranking, setRanking] = useState<any[]>([]);
  const [historico, setHistorico] = useState<any[]>([]);
  const [modelos, setModelos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  async function carregar() {
    setLoading(true);
    try {
      const [s, r, h, m] = await Promise.all([
        getConsumoSaldo(),
        getConsumoRanking(),
        getConsumoHistorico(30),
        getConsumoModelos(),
      ]);
      setSaldo(s);
      setRanking(r);
      setHistorico(h);
      setModelos(m);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { carregar(); }, []);

  const maxGastoAgente = Math.max(...ranking.map((r) => r.gasto_brl), 0.001);
  const maxGastoModelo = Math.max(...modelos.map((m) => m.gasto_brl), 0.001);
  const maxHistorico   = Math.max(...historico.map((h) => h.gasto_brl), 0.001);

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Administrativo</h1>
          <p className="text-zinc-400 mt-1">Consumo de API e orçamento LLM — mês corrente</p>
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
          {/* Cards de saldo */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-xs font-medium text-zinc-400">Gasto no Mês</CardTitle>
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
                <CardTitle className="text-xs font-medium text-zinc-400">Uso do Orçamento</CardTitle>
                <BarChart2 size={14} className="text-zinc-500" />
              </CardHeader>
              <CardContent>
                <div className="mt-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      saldo.percentual_usado >= 80
                        ? "bg-red-500"
                        : saldo.percentual_usado >= 60
                        ? "bg-yellow-500"
                        : "bg-green-500"
                    }`}
                    style={{ width: `${saldo.percentual_usado}%` }}
                  />
                </div>
                <p className="text-xs text-zinc-500 mt-2">{saldo.mes_referencia}</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Ranking por agente */}
            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">Gasto por Agente</CardTitle>
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
                        <div
                          className="h-full bg-blue-500 rounded-full"
                          style={{ width: `${pct(r.gasto_brl, maxGastoAgente)}%` }}
                        />
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
                        <span className="text-zinc-200 font-medium truncate max-w-[180px]" title={m.modelo}>
                          {m.modelo}
                        </span>
                        <div className="flex items-center gap-3 text-zinc-400 text-xs">
                          <span>{(m.tokens_total / 1000).toFixed(0)}k tok</span>
                          <span className="text-white font-medium">R$ {m.gasto_brl.toFixed(4)}</span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-purple-500 rounded-full"
                          style={{ width: `${pct(m.gasto_brl, maxGastoModelo)}%` }}
                        />
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
              <CardTitle className="text-sm font-semibold">Histórico Diário (30 dias)</CardTitle>
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
        </>
      ) : (
        <div className="text-zinc-500">Erro ao carregar dados. Verifique se o backend está online.</div>
      )}
    </div>
  );
}
