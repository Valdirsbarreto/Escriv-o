"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CalendarPlus, Calendar, Clock, MapPin, User, ExternalLink, Loader2, AlertCircle, Trash2, ChevronRight } from "lucide-react";
import { IntimacaoUploadModal } from "@/components/IntimacaoUploadModal";
import Link from "next/link";

interface Intimacao {
  id: string;
  inquerito_id: string | null;
  intimado_nome: string | null;
  intimado_cpf: string | null;
  intimado_qualificacao: string | null;
  numero_inquerito_extraido: string | null;
  data_oitiva: string | null;
  local_oitiva: string | null;
  google_event_id: string | null;
  google_event_url: string | null;
  status: string;
  created_at: string;
}

const STATUS_LABEL: Record<string, { label: string; className: string }> = {
  agendada: { label: "Agendada", className: "bg-blue-500/15 text-blue-400 border-blue-500/20" },
  realizada: { label: "Realizada", className: "bg-green-500/15 text-green-400 border-green-500/20" },
  cancelada: { label: "Cancelada", className: "bg-zinc-700/40 text-zinc-500 border-zinc-600/20" },
  erro_agenda: { label: "Erro no Agenda", className: "bg-red-500/15 text-red-400 border-red-500/20" },
};

const QUAL_LABEL: Record<string, string> = {
  testemunha: "Testemunha",
  investigado: "Investigado",
  vitima: "Vítima",
  perito: "Perito",
  outro: "Outro",
};

function formatData(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  });
}

function groupByMonth(intimacoes: Intimacao[]) {
  const groups: Record<string, Intimacao[]> = {};
  for (const i of intimacoes) {
    const key = i.data_oitiva
      ? new Date(i.data_oitiva).toLocaleDateString("pt-BR", { month: "long", year: "numeric", timeZone: "America/Sao_Paulo" })
      : "Sem data";
    if (!groups[key]) groups[key] = [];
    groups[key].push(i);
  }
  return groups;
}

export default function IntimacoesPAge() {
  const [intimacoes, setIntimacoes] = useState<Intimacao[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [deletando, setDeletando] = useState<string | null>(null);

  const carregar = async () => {
    setLoading(true);
    setErro("");
    try {
      const res = await api.get("/intimacoes");
      setIntimacoes(res.data);
    } catch {
      setErro("Erro ao carregar intimações.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { carregar(); }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Cancelar esta intimação? O evento no Google Agenda também será removido.")) return;
    setDeletando(id);
    try {
      await api.delete(`/intimacoes/${id}`);
      setIntimacoes((prev) => prev.filter((i) => i.id !== id));
    } catch {
      alert("Erro ao cancelar.");
    } finally {
      setDeletando(null);
    }
  };

  const grupos = groupByMonth(intimacoes);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Calendar size={24} className="text-blue-400" />
            Intimações
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Oitivas agendadas automaticamente no Google Agenda
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <CalendarPlus size={16} />
          Lançar Intimação
        </button>
      </div>

      {/* Conteúdo */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-zinc-500" />
        </div>
      )}

      {erro && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
          <AlertCircle size={16} />
          {erro}
        </div>
      )}

      {!loading && !erro && intimacoes.length === 0 && (
        <div className="text-center py-20 text-zinc-600">
          <Calendar size={40} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">Nenhuma intimação lançada ainda.</p>
          <p className="text-xs mt-1">Clique em "Lançar Intimação" para começar.</p>
        </div>
      )}

      {!loading && Object.entries(grupos).map(([mes, items]) => (
        <div key={mes} className="mb-8">
          <h2 className="text-xs uppercase tracking-widest text-zinc-500 font-semibold mb-3 capitalize">
            {mes}
          </h2>
          <div className="space-y-3">
            {items.map((intim) => {
              const st = STATUS_LABEL[intim.status] ?? STATUS_LABEL.agendada;
              return (
                <div
                  key={intim.id}
                  className="border border-zinc-800 rounded-xl p-4 bg-zinc-900/40 hover:bg-zinc-900/70 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-2 flex-1 min-w-0">
                      {/* Nome + qualificação */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-zinc-100 flex items-center gap-1.5">
                          <User size={14} className="text-zinc-500 shrink-0" />
                          {intim.intimado_nome ?? <span className="text-zinc-500 italic">Nome não extraído</span>}
                        </span>
                        {intim.intimado_qualificacao && (
                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-400">
                            {QUAL_LABEL[intim.intimado_qualificacao] ?? intim.intimado_qualificacao}
                          </span>
                        )}
                        <span className={`text-[11px] px-2 py-0.5 rounded-full border ${st.className}`}>
                          {st.label}
                        </span>
                      </div>

                      {/* Data, local, inquérito */}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
                        {intim.data_oitiva && (
                          <span className="flex items-center gap-1">
                            <Clock size={12} />
                            {formatData(intim.data_oitiva)}
                          </span>
                        )}
                        {intim.local_oitiva && (
                          <span className="flex items-center gap-1 truncate max-w-xs">
                            <MapPin size={12} className="shrink-0" />
                            {intim.local_oitiva}
                          </span>
                        )}
                        {intim.numero_inquerito_extraido && (
                          <span className="flex items-center gap-1">
                            IP {intim.numero_inquerito_extraido}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Ações */}
                    <div className="flex items-center gap-2 shrink-0">
                      {intim.google_event_url && (
                        <a
                          href={intim.google_event_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 text-zinc-500 hover:text-blue-400 transition-colors"
                          title="Ver no Google Agenda"
                        >
                          <ExternalLink size={15} />
                        </a>
                      )}
                      {intim.inquerito_id && (
                        <Link
                          href={`/inqueritos/${intim.inquerito_id}`}
                          className="p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors"
                          title="Abrir inquérito"
                        >
                          <ChevronRight size={15} />
                        </Link>
                      )}
                      <button
                        onClick={() => handleDelete(intim.id)}
                        disabled={deletando === intim.id}
                        className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors disabled:opacity-40"
                        title="Cancelar intimação"
                      >
                        {deletando === intim.id ? (
                          <Loader2 size={15} className="animate-spin" />
                        ) : (
                          <Trash2 size={15} />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {showModal && (
        <IntimacaoUploadModal
          onClose={() => setShowModal(false)}
          onSuccess={() => {
            setShowModal(false);
            setTimeout(carregar, 2000); // recarrega após 2s para dar tempo ao worker
          }}
        />
      )}
    </div>
  );
}
