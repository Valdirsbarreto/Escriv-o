"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, FolderOpen, AlertCircle, Clock } from "lucide-react";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export default function Home() {
  const [inqueritos, setInqueritos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/inqueritos")
      .then((res) => setInqueritos(res.data))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard Investigativo</h1>
        <p className="text-zinc-400 mt-2">Visão geral dos inquéritos e atividades recentes do Escrivão AI.</p>
      </div>

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
              <Card key={inq.id} className="bg-zinc-900 border-zinc-800 hover:border-blue-500/50 transition-colors cursor-pointer group">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center justify-between">
                    {inq.numero_procedimento || "S/ Número"}
                    <Badge variant="outline" className="bg-zinc-800 text-zinc-300 border-zinc-700">
                      {inq.estado_atual}
                    </Badge>
                  </CardTitle>
                  <CardDescription className="line-clamp-2 mt-2 text-zinc-400">
                    {inq.titulo || "Inquérito sem título"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center text-sm text-zinc-500 gap-4">
                    <span className="flex items-center gap-1">
                      <FolderOpen className="w-4 h-4" /> {inq.total_paginas || 0} páginas
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-4 h-4" /> Editado recém
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
