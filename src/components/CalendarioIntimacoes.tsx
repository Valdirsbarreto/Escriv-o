"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface Intimacao {
  id: string;
  data_oitiva: string | null;
  status: string;
}

interface CalendarioIntimacoesProps {
  intimacoes: Intimacao[];
  diaSelecionado: string | null; // "YYYY-MM-DD"
  onDiaClick: (dia: string | null) => void;
}

const STATUS_COR: Record<string, string> = {
  agendada: "bg-blue-400",
  data_passada: "bg-amber-400",
  dados_incompletos: "bg-orange-400",
  sem_calendario: "bg-yellow-400",
  realizada: "bg-green-400",
  cancelada: "bg-zinc-500",
  processando: "bg-zinc-600",
  erro_agenda: "bg-red-400",
};

const DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

function toLocalDate(iso: string): Date {
  // Interpreta como horário local (sem conversão de fuso)
  return new Date(iso.replace("T", " ").substring(0, 16));
}

function isoDay(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function CalendarioIntimacoes({
  intimacoes,
  diaSelecionado,
  onDiaClick,
}: CalendarioIntimacoesProps) {
  const hoje = new Date();
  const [mes, setMes] = useState(() => new Date(hoje.getFullYear(), hoje.getMonth(), 1));

  // Agrupa intimações por dia
  const porDia = new Map<string, Intimacao[]>();
  for (const intim of intimacoes) {
    if (!intim.data_oitiva) continue;
    const dia = isoDay(toLocalDate(intim.data_oitiva));
    if (!porDia.has(dia)) porDia.set(dia, []);
    porDia.get(dia)!.push(intim);
  }

  // Dias do grid
  const primeiroDia = new Date(mes.getFullYear(), mes.getMonth(), 1);
  const ultimoDia = new Date(mes.getFullYear(), mes.getMonth() + 1, 0);
  const inicioPad = primeiroDia.getDay(); // 0=Dom
  const totalCelulas = inicioPad + ultimoDia.getDate();
  const linhas = Math.ceil(totalCelulas / 7);

  const celulas: (number | null)[] = [
    ...Array(inicioPad).fill(null),
    ...Array.from({ length: ultimoDia.getDate() }, (_, i) => i + 1),
    ...Array(linhas * 7 - totalCelulas).fill(null),
  ];

  const mesNome = mes.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  const hojeStr = isoDay(hoje);

  const irMesAnterior = () => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1));
  const irMesSeguinte = () => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1));

  // Navega para o mês que contém o dia selecionado ao clicar numa intimação externa
  // (via useEffect no pai — aqui apenas mostramos)

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4">
      {/* Cabeçalho do mês */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={irMesAnterior}
          className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-sm font-semibold text-zinc-200 capitalize">{mesNome}</span>
        <button
          onClick={irMesSeguinte}
          className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* Cabeçalho dias da semana */}
      <div className="grid grid-cols-7 mb-1">
        {DIAS_SEMANA.map((d) => (
          <div key={d} className="text-center text-xs text-zinc-600 font-medium py-1">
            {d}
          </div>
        ))}
      </div>

      {/* Grid de dias */}
      <div className="grid grid-cols-7 gap-y-0.5">
        {celulas.map((dia, idx) => {
          if (dia === null) return <div key={idx} />;

          const diaStr = `${mes.getFullYear()}-${String(mes.getMonth() + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
          const intimsDoDia = porDia.get(diaStr) ?? [];
          const ehHoje = diaStr === hojeStr;
          const ehSelecionado = diaStr === diaSelecionado;
          const temIntimacoes = intimsDoDia.length > 0;

          return (
            <button
              key={idx}
              onClick={() => onDiaClick(ehSelecionado ? null : diaStr)}
              className={`relative flex flex-col items-center justify-start pt-1 pb-2 rounded-lg transition-colors min-h-[44px] ${
                ehSelecionado
                  ? "bg-blue-500/20 ring-1 ring-blue-500/50"
                  : temIntimacoes
                  ? "hover:bg-zinc-800/70 cursor-pointer"
                  : "hover:bg-zinc-800/30 cursor-default"
              }`}
              disabled={!temIntimacoes && !ehSelecionado}
            >
              <span
                className={`text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full ${
                  ehHoje
                    ? "bg-blue-500 text-white"
                    : ehSelecionado
                    ? "text-blue-300"
                    : "text-zinc-400"
                }`}
              >
                {dia}
              </span>

              {/* Pontos coloridos por status */}
              {intimsDoDia.length > 0 && (
                <div className="flex gap-0.5 mt-0.5 flex-wrap justify-center px-1">
                  {intimsDoDia.slice(0, 3).map((intim) => (
                    <span
                      key={intim.id}
                      className={`w-1.5 h-1.5 rounded-full ${STATUS_COR[intim.status] ?? "bg-zinc-500"}`}
                    />
                  ))}
                  {intimsDoDia.length > 3 && (
                    <span className="text-xs text-zinc-500">+{intimsDoDia.length - 3}</span>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Legenda */}
      <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-zinc-800">
        {[
          { cor: "bg-blue-400", label: "Agendada" },
          { cor: "bg-amber-400", label: "Data passada" },
          { cor: "bg-green-400", label: "Realizada" },
          { cor: "bg-orange-400", label: "Incompleta" },
        ].map(({ cor, label }) => (
          <span key={label} className="flex items-center gap-1.5 text-xs text-zinc-500">
            <span className={`w-2 h-2 rounded-full ${cor}`} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
