"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { 
  Search, FolderOpen, AlertCircle, Clock, UploadCloud, 
  ArrowRight, Plus, FilePlus, Filter, LayoutGrid 
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
  DialogTrigger,
} from "@/components/ui/dialog";

export default function Home() {
  const [inqueritos, setInqueritos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  // Formulario novo
  const [novoNum, setNovoNum] = useState("");
  const [novoDel, setNovoDel] = useState("");
  const [novoAno, setNovoAno] = useState(new Date().getFullYear());
  const [novoDesc, setNovoDesc] = useState("");
  const [redistribuido, setRedistribuido] = useState(false);
  const [novoDelAtualCod, setNovoDelAtualCod] = useState("");
  const [criando, setCriando] = useState(false);

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

  const handleCriar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!novoNum || !novoDel) return;
    setCriando(true);
    try {
      await api.post("/inqueritos/", {
        numero: novoNum,
        delegacia: novoDel,
        ano: novoAno,
        descricao: novoDesc,
        prioridade: "normal",
        redistribuido: redistribuido,
        delegacia_atual_codigo: redistribuido ? novoDelAtualCod : undefined
      });
      setIsDialogOpen(false);
      setNovoNum("");
      setNovoDesc("");
      fetchInqueritos();
    } catch (e) {
      console.error(e);
    } finally {
      setCriando(false);
    }
  };

  const filteredInqueritos = inqueritos.filter(inq => 
    (inq.numero || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
    (inq.descricao || "").toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-10 animate-in fade-in duration-700">
      
      {/* Header com Ações */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-1">
          <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
            Gestão Investigativa
          </h1>
          <p className="text-zinc-500 text-lg max-w-2xl">
            Central de comando e monitoramento de inquéritos policiais do Escrivão AI.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger className="bg-zinc-100 text-zinc-900 hover:bg-white font-semibold h-11 px-6 rounded-xl transition-all hover:scale-105 active:scale-95 shadow-lg shadow-white/5 flex items-center">
              <Plus size={18} className="mr-2" /> Novo Procedimento
            </DialogTrigger>
            <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle className="text-xl">Instaurar Inquérito</DialogTitle>
                <DialogDescription className="text-zinc-500">
                  Defina os dados estruturais do novo caso para análise.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCriar} className="space-y-4 pt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Número</label>
                    <Input required placeholder="Ex: 123" value={novoNum} onChange={(e) => setNovoNum(e.target.value)}
                      className="bg-zinc-900 border-zinc-800 focus:border-blue-500 transition-colors" />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Ano</label>
                    <Input type="number" required value={novoAno} onChange={(e) => setNovoAno(parseInt(e.target.value))}
                      className="bg-zinc-900 border-zinc-800" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Delegacia</label>
                  <Input required placeholder="Ex: DDEF" value={novoDel} onChange={(e) => setNovoDel(e.target.value)}
                    className="bg-zinc-900 border-zinc-800" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm text-zinc-400 flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={redistribuido} onChange={(e) => setRedistribuido(e.target.checked)}
                      className="rounded border-zinc-800 bg-zinc-900 checked:bg-blue-500" />
                    Inquérito redistribuído
                  </label>
                </div>
                {redistribuido && (
                  <Input placeholder="Código DP Destino" value={novoDelAtualCod} onChange={(e) => setNovoDelAtualCod(e.target.value)}
                    className="bg-zinc-900 border-blue-900/50" />
                )}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Resumo Inicial</label>
                  <Input placeholder="Fato principal" value={novoDesc} onChange={(e) => setNovoDesc(e.target.value)}
                    className="bg-zinc-900 border-zinc-800" />
                </div>
                <Button type="submit" disabled={criando} className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold h-12 rounded-xl mt-4">
                  {criando ? "Salvando..." : "Finalizar Instalação"}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Grid de Atalhos Rápidos */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Link href="/ingestao" className="md:col-span-2 group">
          <Card className="relative overflow-hidden border-blue-500/20 bg-gradient-to-br from-blue-950/40 via-zinc-900/90 to-zinc-950 p-1 transition-all hover:border-blue-400/40 hover:scale-[1.01] h-full">
            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/10 rounded-full blur-[80px] pointer-events-none" />
            <CardContent className="relative p-6 flex flex-col h-full justify-between">
              <div className="flex items-start justify-between">
                <div className="p-3 bg-blue-500/20 rounded-2xl border border-blue-500/30">
                  <UploadCloud className="w-8 h-8 text-blue-400" />
                </div>
                <ArrowRight className="w-6 h-6 text-zinc-700 group-hover:text-blue-400 group-hover:translate-x-2 transition-all" />
              </div>
              <div className="mt-8">
                <h3 className="text-2xl font-bold text-white mb-2">Ingestão Automática</h3>
                <p className="text-zinc-400">Arraste seus autos (PDF/TIFF) para que a IA crie o procedimento, extraia personagens e sugira diligências instantaneamente.</p>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Card className="bg-zinc-900/50 border-zinc-800 flex flex-col justify-between">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Procedimentos Ativos</CardTitle>
              <LayoutGrid className="w-4 h-4 text-zinc-600" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-6xl font-black text-white">{inqueritos.length}</div>
            <p className="text-zinc-500 text-sm mt-2">IPs sob custódia digital</p>
          </CardContent>
        </Card>
      </div>

      {/* Lista de Inquéritos */}
      <div className="space-y-6 pt-4">
        <div className="flex flex-col md:flex-row gap-4 items-center justify-between translate-y-2">
          <div className="relative flex-1 max-w-xl w-full group">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500 group-focus-within:text-blue-400 transition-colors" />
            <Input
              type="search"
              placeholder="Pesquisar por número, DP, vítima ou investigado..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-zinc-950 border-zinc-800 pl-10 h-12 rounded-xl focus:border-blue-500/50 transition-all"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" className="border-zinc-800 text-zinc-500 gap-2 h-10 hover:bg-zinc-900">
              <Filter size={14} /> Filtros
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-full py-20 text-center animate-pulse">
              <FolderOpen className="mx-auto h-12 w-12 text-zinc-800 mb-4" />
              <p className="text-zinc-500 font-medium tracking-wide">Sincronizando arquivos do cartório...</p>
            </div>
          ) : filteredInqueritos.length === 0 ? (
            <div className="col-span-full py-24 text-center border-2 border-dashed border-zinc-900 rounded-3xl">
              <AlertCircle className="mx-auto h-12 w-12 text-zinc-800 mb-4" />
              <p className="text-zinc-500 text-lg">Nenhum inquérito encontrado para esta busca.</p>
            </div>
          ) : (
            filteredInqueritos.map((inq) => (
              <Link key={inq.id} href={`/inqueritos/${inq.id}`} className="block group">
                <Card className="bg-zinc-950 border-zinc-900 hover:border-blue-500/30 transition-all cursor-pointer h-full relative overflow-hidden group-hover:shadow-[0_0_20px_rgba(59,130,246,0.05)]">
                  <div className="absolute top-0 left-0 w-1 h-full bg-blue-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                  <CardHeader className="pb-3 px-6 pt-6">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-xs font-black text-blue-500/50 uppercase tracking-tighter">IP {inq.ano || "2024"}</span>
                      <Badge className={`rounded-md px-1.5 py-0.5 text-[10px] uppercase font-bold tracking-widest ${
                        inq.estado_atual === 'completo' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                      }`}>
                        {inq.estado_atual}
                      </Badge>
                    </div>
                    <CardTitle className="text-xl font-bold text-zinc-100 tracking-tight group-hover:text-white transition-colors">
                      {inq.numero}
                    </CardTitle>
                    <CardDescription className="line-clamp-2 mt-2 text-zinc-500 text-sm leading-relaxed min-h-[40px]">
                      {inq.descricao || "Procedimento aguardando triagem detalhada."}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="px-6 pb-6 pt-2">
                    <div className="flex items-center justify-between pt-4 border-t border-zinc-900">
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1.5 text-xs text-zinc-500">
                          <FilePlus size={14} className="text-zinc-600" /> {inq.total_documentos || 0}
                        </span>
                        <span className="flex items-center gap-1.5 text-xs text-zinc-500">
                          <AlertCircle size={14} className="text-zinc-600" /> 0
                        </span>
                      </div>
                      <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-widest">
                        {new Date(inq.created_at).toLocaleDateString("pt-BR", {month: 'short', day: 'numeric'})}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
