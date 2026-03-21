"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, FolderOpen, AlertCircle, Clock, UploadCloud, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export default function Home() {
  const [inqueritos, setInqueritos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/inqueritos")
      .then((res) => setInqueritos(res.data?.items ?? res.data))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard Investigativo</h1>
        <p className="text-zinc-400 mt-2">Visão geral dos inquéritos e atividades recentes do Escrivão AI.</p>
      </div>

      {/* Banner de Ingestão Rápida */}
      <Link href="/ingestao" className="block group">
        <div className="relative overflow-hidden rounded-2xl border border-blue-500/30 bg-gradient-to-r from-blue-950/60 via-zinc-900/80 to-zinc-900/60 p-6 transition-all hover:border-blue-400/60 hover:from-blue-950/80">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(59,130,246,0.15),_transparent_60%)]" />
          <div className="relative flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-blue-500/20 rounded-xl border border-blue-500/30">
                <UploadCloud className="w-6 h-6 text-blue-400" />
              </div>
              <div>
                <p className="font-semibold text-white text-lg">Importar Novo Inquérito</p>
                <p className="text-zinc-400 text-sm mt-0.5">
                  Arraste PDFs, imagens ou scans. A IA detecta e cria o processo automaticamente.
                </p>
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-blue-400 shrink-0 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>
      </Link>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Inquéritos Ativos</CardTitle>
            <FolderOpen className="h-4 w-4 text-zinc-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{inqueritos.length}</div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <div className="flex gap-4 items-center">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-zinc-500" />
            <Input
              type="search"
              placeholder="Buscar por número, pessoa ou empresa..."
              className="w-full bg-zinc-900 border-zinc-800 pl-9"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {loading ? (
            <div className="text-zinc-500 col-span-3">Carregando inquéritos...</div>
          ) : inqueritos.length === 0 ? (
            <div className="text-zinc-500 col-span-3">Nenhum inquérito encontrado.</div>
          ) : (
            inqueritos.map((inq) => (
              <Link key={inq.id} href={`/inqueritos/${inq.id}`} className="block group">
                <Card className="bg-zinc-900 border-zinc-800 hover:border-blue-500/50 transition-colors cursor-pointer h-full">
                  <CardHeader>
                    <CardTitle className="text-lg flex items-center justify-between">
                      {inq.numero || "S/ Número"}
                      <Badge variant="outline" className={`border-zinc-700 text-xs ${inq.numero?.startsWith("TEMP-") ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/30" : "bg-zinc-800 text-zinc-300"}`}>
                        {inq.estado_atual}
                      </Badge>
                    </CardTitle>
                    <CardDescription className="line-clamp-2 mt-2 text-zinc-400">
                      {inq.descricao || "Inquérito sem descrição"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center text-sm text-zinc-500 gap-4">
                      <span className="flex items-center gap-1">
                        <FolderOpen className="w-4 h-4" /> {inq.total_documentos || 0} arquivos
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-4 h-4" /> {new Date(inq.created_at).toLocaleDateString("pt-BR")}
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
