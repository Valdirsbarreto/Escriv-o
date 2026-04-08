"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Search, FolderOpen, AlertCircle, Clock, UploadCloud,
  ArrowRight, FilePlus, Filter, LayoutGrid, Edit2, FileSearch
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function Home() {
  const [inqueritos, setInqueritos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  // Estado para Edição Rápida
  const [editInquerito, setEditInquerito] = useState<any | null>(null);
  const [novoNumero, setNovoNumero] = useState("");
  const [salvando, setSalvando] = useState(false);

  const fetchInqueritos = () => {
    setLoading(true);
    api.get("/inqueritos")
      .then((res) => setInqueritos(res.data?.items ?? res.data))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchInqueritos();
  }, []);

  const handleSalvarIP = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editInquerito || !novoNumero) return;
    setSalvando(true);
    try {
      // Atualiza apenas o número do inquérito
      await api.patch(`/inqueritos/${editInquerito.id}/numero`, { numero: novoNumero });
      setEditInquerito(null);
      fetchInqueritos();
    } catch (e) {
      console.error(e);
      alert("Erro ao atualizar o número do inquérito.");
    } finally {
      setSalvando(false);
    }
  };

  const filteredInqueritos = inqueritos.filter(inq => 
    (inq.numero || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
    (inq.descricao || "").toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-10 animate-in fade-in duration-700">
      
      {/* Header Minimalista */}
      <div className="space-y-1">
        <h1 className="text-4xl font-extrabold tracking-tight text-white mb-2">
          Gestão Investigativa
        </h1>
        <p className="text-zinc-500 text-lg max-w-2xl">
          Central de comando e monitoramento de inquéritos policiais do Escrivão AI.
        </p>
      </div>

      {/* Seção Principal: Ingestão e Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Link href="/ingestao" className="lg:col-span-2 group">
          <Card className="relative h-full overflow-hidden border-blue-400/20 bg-gradient-to-br from-blue-950/40 via-zinc-900/95 to-zinc-950 p-1 transition-all hover:border-blue-400/40 hover:scale-[1.005] active:scale-[0.995]">
            <div className="absolute top-0 right-0 w-80 h-80 bg-blue-500/5 rounded-full blur-[100px] pointer-events-none" />
            <CardContent className="relative p-8 flex flex-col h-full justify-between">
              <div className="flex items-start justify-between">
                <div className="p-4 bg-blue-500/10 rounded-2xl border border-blue-500/20">
                  <UploadCloud className="w-8 h-8 text-blue-400" />
                </div>
                <div className="bg-blue-500/10 text-blue-400 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border border-blue-500/20">
                  Fluxo Principal
                </div>
              </div>
              <div className="mt-12">
                <h3 className="text-3xl font-black text-white mb-3">Ingestão Automática</h3>
                <p className="text-zinc-400 text-base leading-relaxed max-w-xl">
                  Arraste seus autos (PDF/TIFF) para que a IA processe a capa, extraia o número do IP e qualifique os alvos imediatamente.
                </p>
                <div className="mt-8 flex items-center gap-2 text-blue-400 font-semibold group-hover:gap-4 transition-all uppercase tracking-widest text-xs">
                  Iniciar Procedimento <ArrowRight size={16} />
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Card className="bg-zinc-900/40 border-zinc-800 flex flex-col justify-between backdrop-blur-sm">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-xs font-bold text-zinc-500 uppercase tracking-[0.2em]">Sincronizados</CardTitle>
              <LayoutGrid className="w-4 h-4 text-zinc-700" />
            </div>
          </CardHeader>
          <CardContent className="pb-10">
            <div className="text-7xl font-black text-white tracking-tighter tabular-nums drop-shadow-2xl">
              {inqueritos.length}
            </div>
            <p className="text-zinc-500 text-sm font-medium mt-4 flex items-center gap-2">
               <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" /> Monitoramento Ativo
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Lista de Inquéritos */}
      <div className="space-y-8 animate-in slide-in-from-bottom-4 duration-1000 delay-200">
        <div className="flex flex-col md:flex-row gap-4 items-center justify-between">
          <div className="relative flex-1 max-w-xl w-full group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500 group-focus-within:text-blue-400 transition-colors" />
            <Input
              type="search"
              placeholder="Pesquisar por número, DP ou resumo..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-zinc-950 border-zinc-800 pl-11 h-14 rounded-2xl focus:border-blue-500/40 transition-all text-base"
            />
          </div>
          <Button variant="outline" className="border-zinc-800 text-zinc-400 gap-2 h-14 px-6 rounded-2xl hover:bg-zinc-900">
            <Filter size={16} /> Filtros
          </Button>
          <Link href="/agentes/osint?avulsa=1">
            <Button variant="outline" className="border-zinc-700 text-zinc-300 gap-2 h-14 px-6 rounded-2xl hover:bg-zinc-900 hover:border-blue-500/40">
              <FileSearch size={16} /> Consulta Avulsa
            </Button>
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-full py-20 text-center">
              <FolderOpen className="mx-auto h-12 w-12 text-zinc-800 mb-4 animate-bounce" />
              <p className="text-zinc-600 font-bold uppercase tracking-widest text-xs">Sincronizando Dados...</p>
            </div>
          ) : filteredInqueritos.length === 0 ? (
            <div className="col-span-full py-32 text-center border-2 border-dashed border-zinc-900 rounded-[32px]">
              <AlertCircle className="mx-auto h-12 w-12 text-zinc-800 mb-4" />
              <p className="text-zinc-500 text-lg">Nenhum inquérito encontrado.</p>
            </div>
          ) : (
            filteredInqueritos.map((inq) => (
              <div key={inq.id} className="relative group">
                <Link href={`/inqueritos/${inq.id}`} className="block h-full">
                  <Card className="bg-zinc-950/80 border-zinc-900 hover:border-blue-500/40 transition-all cursor-pointer h-full relative overflow-hidden group-hover:-translate-y-1 group-hover:shadow-[0_15px_30px_-10px_rgba(59,130,246,0.1)]">
                    <CardHeader className="p-8">
                      <div className="flex justify-between items-start mb-6">
                        <Badge className="bg-zinc-900 text-zinc-500 border-zinc-800 uppercase text-[9px] font-black tracking-widest px-2 py-1">
                          IP {inq.ano || "2024"}
                        </Badge>
                        <Badge className={`rounded-full px-3 py-1 text-[9px] uppercase font-black tracking-widest ${
                          inq.estado_atual === 'completo' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                        }`}>
                          {inq.estado_atual}
                        </Badge>
                      </div>
                      <CardTitle className="text-2xl font-black text-zinc-100 tracking-tight mb-3 transition-colors group-hover:text-white">
                        {inq.numero}
                      </CardTitle>
                      <CardDescription className="line-clamp-2 text-zinc-500 text-sm leading-relaxed mb-6 h-10">
                        {inq.descricao || "Aguardando análise de IA para extração de fatos principais."}
                      </CardDescription>
                      <div className="flex items-center justify-between pt-6 border-t border-zinc-900">
                        <div className="flex items-center gap-4">
                          <span className="flex items-center gap-2 text-xs font-bold text-zinc-600">
                            <FilePlus size={14} /> {inq.total_documentos || 0} docs
                          </span>
                        </div>
                        <span className="text-[10px] font-black text-zinc-700 uppercase">
                          {new Date(inq.created_at).toLocaleDateString("pt-BR")}
                        </span>
                      </div>
                    </CardHeader>
                  </Card>
                </Link>

                {/* Edição Rápida de Número */}
                <button 
                  onClick={(e) => {
                    e.preventDefault(); e.stopPropagation();
                    setEditInquerito(inq); setNovoNumero(inq.numero);
                  }}
                  className="absolute top-6 right-6 p-2.5 bg-zinc-900 border border-zinc-800 rounded-xl text-zinc-500 hover:text-blue-400 hover:border-blue-500/40 opacity-0 group-hover:opacity-100 transition-all z-20 shadow-xl"
                  title="Corrigir número"
                >
                  <Edit2 size={16} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Dialog para Correção */}
      <Dialog open={!!editInquerito} onOpenChange={(open) => !open && setEditInquerito(null)}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 sm:max-w-[440px] rounded-3xl p-8 shadow-2xl">
          <DialogHeader className="space-y-3">
            <DialogTitle className="text-2xl font-bold flex items-center gap-3">
              <Edit2 className="text-blue-500" size={24} /> Corrigir Registro
            </DialogTitle>
            <DialogDescription className="text-zinc-500 text-base leading-relaxed">
              O Agente IA pode ter se equivocado na leitura. Insira o número correto conforme consta na capa dos autos.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSalvarIP} className="space-y-6 pt-6">
            <div className="space-y-2">
              <label className="text-xs font-black text-zinc-600 uppercase tracking-widest pl-1">Número do IP (Correto)</label>
              <Input 
                value={novoNumero} 
                onChange={(e) => setNovoNumero(e.target.value)}
                placeholder="Ex: 911-01234/2024"
                className="bg-zinc-900 border-zinc-800 h-14 rounded-2xl focus:border-blue-500 transition-all text-xl font-mono text-blue-400"
                autoFocus
              />
            </div>
            <DialogFooter className="gap-3 pt-6">
              <Button type="button" variant="ghost" onClick={() => setEditInquerito(null)} className="h-12 rounded-xl text-zinc-500 hover:text-white">
                Cancelar
              </Button>
              <Button type="submit" disabled={salvando} className="bg-blue-600 hover:bg-blue-500 text-white font-bold h-12 px-8 rounded-xl flex-1 shadow-lg shadow-blue-500/20">
                {salvando ? "Salvando..." : "Confirmar Mudança"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
