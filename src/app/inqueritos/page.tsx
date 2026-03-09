"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/store/app";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FolderOpen, Plus, Search, Clock, FilePlus } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

export default function InqueritosPage() {
  const router = useRouter();
  const { setInqueritoAtivoId } = useAppStore();
  const [inqueritos, setInqueritos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

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
      .then((res) => setInqueritos(res.data.items || res.data))
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
      const resp = await api.post("/inqueritos/", {
        numero: novoNum,
        delegacia: novoDel || undefined,
        ano: novoAno,
        descricao: novoDesc,
        prioridade: "normal",
        classificacao_estrategica: "padrao",
        redistribuido: redistribuido,
        delegacia_atual_codigo: redistribuido ? novoDelAtualCod : undefined
      });
      setIsDialogOpen(false);
      setNovoNum("");
      setNovoDesc("");
      fetchInqueritos();
      // Opcional: já pular para a página do inquérito novo
    } catch (e) {
      console.error(e);
      alert("Erro ao criar inquérito.");
    } finally {
      setCriando(false);
    }
  };

  const abrirInquerito = (id: string) => {
    setInqueritoAtivoId(id);
    router.push(`/inqueritos/${id}`);
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <FolderOpen className="text-blue-500" />
            Inquéritos
          </h1>
          <p className="text-zinc-400 mt-2">
            Gerencie os procedimentos investigativos e acesse os autos digitais.
          </p>
        </div>
        
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger className="bg-blue-600 hover:bg-blue-700 h-10 px-4 text-white font-medium flex gap-2 items-center rounded-md">
             <Plus size={18} /> Novo Procedimento
          </DialogTrigger>
          <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Instaurar Novo Inquérito</DialogTitle>
              <DialogDescription className="text-zinc-400">
                Preencha os dados básicos para inicializar o repositório deste caso no Escrivão AI.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCriar} className="space-y-4 pt-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-zinc-300">Número</label>
                  <Input 
                    required placeholder="Ex: 123" 
                    value={novoNum} onChange={(e) => setNovoNum(e.target.value)}
                    className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-zinc-300">Ano</label>
                  <Input 
                    type="number" required 
                    value={novoAno} onChange={(e) => setNovoAno(parseInt(e.target.value))}
                    className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-zinc-300">Delegacia / Órgão</label>
                <Input 
                  required placeholder="Ex: DEF" 
                  value={novoDel} onChange={(e) => setNovoDel(e.target.value)}
                  className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                  <input 
                    type="checkbox" 
                    checked={redistribuido} 
                    onChange={(e) => setRedistribuido(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-900" 
                  />
                  Inquérito redistribuído
                </label>
              </div>
              
              {redistribuido && (
                <div className="space-y-2 border-l-2 border-blue-500 pl-3">
                  <label className="text-sm font-medium text-zinc-300">Código da Delegacia Atual</label>
                  <Input 
                    placeholder="Ex: 910 ou 064" 
                    value={novoDelAtualCod} onChange={(e) => setNovoDelAtualCod(e.target.value)}
                    className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
                  />
                  <p className="text-xs text-zinc-500">
                    O sistema usará apenas o DDD inicial do inquérito como DP de Origem. Preencha aqui a DP de destino.
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <label className="text-sm font-medium text-zinc-300">Resumo dos Fatos</label>
                <Input 
                  placeholder="Objeto principal da investigação" 
                  value={novoDesc} onChange={(e) => setNovoDesc(e.target.value)}
                  className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
                />
              </div>
              <DialogFooter className="pt-4">
                <Button type="submit" disabled={criando} className="bg-blue-600 hover:bg-blue-700 w-full">
                  {criando ? "Salvando..." : "Criar Inquérito"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex gap-4 items-center">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-zinc-500" />
          <Input
            type="search"
            placeholder="Filtrar inquéritos..."
            className="w-full bg-zinc-900 border-zinc-800 pl-9"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {loading ? (
          <div className="text-zinc-500 col-span-3">Consultando base de dados...</div>
        ) : inqueritos.length === 0 ? (
          <div className="text-zinc-500 col-span-3 text-center py-12 bg-zinc-900/50 rounded-xl border border-zinc-800 border-dashed">
            <FolderOpen className="mx-auto h-12 w-12 text-zinc-700 mb-4" />
            <h3 className="text-lg font-medium text-zinc-300">Nenhum inquérito encontrado</h3>
            <p className="mt-1">Clique em "Novo Procedimento" para começar.</p>
          </div>
        ) : (
          inqueritos.map((inq) => (
            <Card 
              key={inq.id} 
              onClick={() => abrirInquerito(inq.id)}
              className="bg-zinc-900 border-zinc-800 hover:border-blue-500/50 transition-all cursor-pointer group hover:shadow-lg hover:shadow-blue-500/5"
            >
              <CardHeader>
                <CardTitle className="text-lg flex items-center justify-between">
                  <span className="font-semibold text-zinc-100 group-hover:text-blue-400 transition-colors flex items-center gap-2">
                    {inq.numero}/{inq.ano} 
                    {inq.redistribuido && <Badge variant="outline" className="text-blue-400 border-blue-400/30 bg-blue-400/10 text-[10px]">REDIST</Badge>}
                  </span>
                  <Badge variant="outline" className="bg-zinc-800 text-zinc-300 border-zinc-700">
                    {inq.estado_atual}
                  </Badge>
                </CardTitle>
                <CardDescription className="line-clamp-2 mt-2 text-zinc-400">
                  <span className="block text-xs font-medium text-zinc-300 mb-1">
                    {inq.redistribuido ? `Atual: ${inq.delegacia_atual_nome || inq.delegacia_atual_codigo || inq.delegacia}` : (inq.delegacia_origem_nome || inq.delegacia)}
                  </span>
                  {inq.descricao || "Sem resumo fático"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex justify-between items-center text-sm text-zinc-500 border-t border-zinc-800/50 pt-4 mt-2">
                  <span className="flex items-center gap-1">
                    <FilePlus className="w-4 h-4" /> {inq.total_documentos || 0} docs
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-4 h-4" /> {new Date(inq.updated_at).toLocaleDateString()}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
