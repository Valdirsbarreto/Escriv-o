"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/store/app";
import { api, getPessoas, getEmpresas, gerarFichaPessoa, gerarFichaEmpresa } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { UserSearch, Bot, Target, AlertTriangle, Building, User } from "lucide-react";

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
      }).finally(() => {
        setLoadingEntidades(false);
      });
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
      console.error(e);
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
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 h-[calc(100vh-2rem)] flex flex-col">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <UserSearch className="text-blue-500" />
          Agente OSINT
        </h1>
        <p className="text-zinc-400 mt-2">
          Gere perfis investigativos profundos (Dossiês Táticos) de pessoas ou empresas cruzando fontes abertas e contexto dos autos.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 flex-1 min-h-0">
        {/* Coluna Esquerda: Conhecimento / Alvos */}
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
                      <button
                        key={p.id}
                        onClick={() => setAlvoSelecionado({id: p.id, tipo: "pessoa"})}
                        className={`w-full text-left px-3 py-2 rounded-md text-sm flex flex-col transition-colors ${
                          alvoSelecionado?.id === p.id 
                            ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" 
                            : "text-zinc-300 hover:bg-zinc-800"
                        }`}
                      >
                        <div className="font-medium flex items-center gap-2"><User size={14}/> {p.nome}</div>
                        {p.cpf && <div className="text-xs text-zinc-500 mt-1">CPF: {p.cpf}</div>}
                      </button>
                    ))}

                    {empresas.length > 0 && <div className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider mt-2">Empresas</div>}
                    {empresas.map((e) => (
                      <button
                        key={e.id}
                        onClick={() => setAlvoSelecionado({id: e.id, tipo: "empresa"})}
                        className={`w-full text-left px-3 py-2 rounded-md text-sm flex flex-col transition-colors ${
                          alvoSelecionado?.id === e.id 
                            ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" 
                            : "text-zinc-300 hover:bg-zinc-800"
                        }`}
                      >
                        <div className="font-medium flex items-center gap-2"><Building size={14}/> {e.nome}</div>
                        {e.cnpj && <div className="text-xs text-zinc-500 mt-1">CNPJ: {e.cnpj}</div>}
                      </button>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>

          <Button 
            className="w-full bg-blue-600 hover:bg-blue-700 h-12"
            disabled={!alvoSelecionado || gerando}
            onClick={handleGerarFicha}
          >
            {gerando ? (
              <span className="flex items-center gap-2"><Bot className="animate-pulse" size={18}/> Processando Inteligência...</span>
            ) : (
              <span className="flex items-center gap-2"><UserSearch size={18}/> Emitir Ficha OSINT</span>
            )}
          </Button>
        </div>

        {/* Coluna Direita: O Dossiê Gerado */}
        <div className="lg:col-span-2 flex flex-col">
          <Card className="bg-zinc-950 border-zinc-800 h-full flex flex-col shadow-2xl relative overflow-hidden">
            {/* Background Glow */}
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
                      {/* JSON Render: O frontend mapeia os campos do dicionário Python */}
                      <div className="flex justify-between items-start">
                        <div>
                          <h2 className="text-2xl font-bold text-zinc-100">{fichaRenderizada.nome || alvoSelecionado?.id}</h2>
                          <div className="flex gap-2 mt-2">
                            <Badge variant="outline" className="border-blue-500/30 text-blue-400 bg-blue-500/5">
                              {fichaRenderizada.risco || "Desconhecido"}
                            </Badge>
                            <Badge variant="outline" className="border-zinc-700 text-zinc-400 bg-zinc-800">
                              Gerado por LLM
                            </Badge>
                          </div>
                        </div>
                      </div>

                      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
                         <h3 className="text-sm font-semibold text-zinc-100 uppercase tracking-wide flex items-center gap-2 mb-3">
                           Resumo Executivo
                         </h3>
                         <p className="text-zinc-300 text-sm leading-relaxed">{fichaRenderizada.resumo || "Não disponível."}</p>
                      </div>

                      {fichaRenderizada.bandeiras_vermelhas && fichaRenderizada.bandeiras_vermelhas.length > 0 && (
                        <div>
                           <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wide flex items-center gap-2 mb-3">
                             <AlertTriangle size={16} /> Bandeiras Vermelhas
                           </h3>
                           <ul className="space-y-2">
                             {fichaRenderizada.bandeiras_vermelhas.map((b: string, i: number) => (
                               <li key={i} className="flex gap-2 text-sm text-zinc-300 bg-red-500/5 border border-red-500/10 p-3 rounded">
                                  <span className="text-red-500 shrink-0">•</span> {b}
                               </li>
                             ))}
                           </ul>
                        </div>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                           <h3 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Vínculos</h3>
                           <div className="space-y-2 text-sm text-zinc-300">
                             {fichaRenderizada.vinculos ? (
                               <pre className="whitespace-pre-wrap font-sans bg-zinc-900 p-3 rounded border border-zinc-800 text-xs">
                                 {JSON.stringify(fichaRenderizada.vinculos, null, 2)}
                               </pre>
                             ) : "Nenhum vínculo detectado."}
                           </div>
                        </div>
                        <div>
                           <h3 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Dados Brutos Analisados</h3>
                           <div className="text-xs text-zinc-500 border border-zinc-800 p-3 rounded bg-zinc-900 overflow-x-auto">
                              JSON Raw Output gerado com sucesso pelo Agente OSINT Premium.
                           </div>
                        </div>
                      </div>
                      
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
