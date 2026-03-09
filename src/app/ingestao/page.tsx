"use client";

import { DropZoneIngestao } from "@/components/DropZoneIngestao";
import { Brain, Zap, ShieldCheck, FileSearch } from "lucide-react";

const FEATURES = [
  {
    icon: Brain,
    title: "IA Orquestradora",
    desc: "Lê os primeiros documentos e identifica o inquérito automaticamente.",
  },
  {
    icon: FileSearch,
    title: "Extração Inteligente",
    desc: "Extrai número do IP, delegacia, datas e personagens do texto.",
  },
  {
    icon: Zap,
    title: "Processamento Rápido",
    desc: "Indexação em background, sem travar sua interface.",
  },
  {
    icon: ShieldCheck,
    title: "Privacidade Total",
    desc: "Dados armazenados localmente, nunca compartilhados com terceiros.",
  },
];

export default function IngestaoPage() {
  return (
    <div className="p-8 max-w-4xl mx-auto space-y-10">
      {/* Cabeçalho */}
      <div>
        <div className="inline-flex items-center gap-2 text-xs font-semibold text-blue-400 bg-blue-500/10 border border-blue-500/20 px-3 py-1.5 rounded-full mb-4">
          <Brain className="w-3.5 h-3.5 animate-pulse" />
          Agente Orquestrador Ativo
        </div>
        <h1 className="text-4xl font-bold tracking-tight text-white">
          Ingestão de Documentos
        </h1>
        <p className="text-zinc-400 mt-3 text-lg leading-relaxed max-w-2xl">
          Envie os arquivos do inquérito (Portaria, BO, Autos) e a IA cria o processo automaticamente,
          extrai as partes envolvidas e gera o relatório inicial.
        </p>
      </div>

      {/* Drop Zone Principal */}
      <div>
        <DropZoneIngestao />
      </div>

      {/* Features */}
      <div>
        <p className="text-xs font-semibold text-zinc-600 uppercase tracking-widest mb-4">
          O que o sistema faz automaticamente
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="flex items-start gap-4 p-4 rounded-xl bg-zinc-900/50 border border-zinc-800"
              >
                <div className="p-2 bg-blue-500/10 rounded-lg shrink-0">
                  <Icon className="w-4 h-4 text-blue-400" />
                </div>
                <div>
                  <p className="font-semibold text-sm text-zinc-200">{f.title}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">{f.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Formatos Aceitos */}
      <div className="border-t border-zinc-800 pt-6">
        <p className="text-xs text-zinc-600">
          <span className="font-semibold text-zinc-500">Formatos aceitos:</span>{" "}
          PDF, PNG, JPG/JPEG, TIFF — Múltiplos arquivos em uma só sessão.
        </p>
      </div>
    </div>
  );
}
