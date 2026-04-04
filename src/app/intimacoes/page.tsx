"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CalendarPlus, Calendar, Clock, MapPin, User, ExternalLink, Loader2, AlertCircle, Trash2, ChevronRight, Pencil, Hash } from "lucide-react";
import { IntimacaoUploadModal } from "@/components/IntimacaoUploadModal";
import { IntimacaoEditModal } from "@/components/IntimacaoEditModal";
import { CalendarioIntimacoes } from "@/components/CalendarioIntimacoes";
import Link from "next/link";
import { useRouter } from "next/navigation";

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
  processando: { label: "Processando...", className: "bg-zinc-700/40 text-zinc-400 border-zinc-600/20" },
  data_passada: { label: "Data passada", className: "bg-amber-500/15 text-amber-400 border-amber-500/20" },
  agendada: { label: "Agendada", className: "bg-blue-500/15 text-blue-400 border-blue-500/20" },
  realizada: { label: "Realizada", className: "bg-green-500/15 text-green-400 border-green-500/20" },
  cancelada: { label: "Cancelada", className: "bg-zinc-700/40 text-zinc-500 border-zinc-600/20" },
  erro_agenda: { label: "Erro no Agenda", className: "bg-red-500/15 text-red-400 border-red-500/20" },
  sem_calendario: { label: "Sem Calendário", className: "bg-yellow-500/15 text-yellow-400 border-yellow-500/20" },
  dados_incompletos: { label: "Dados incompletos", className: "bg-orange-500/15 text-orange-400 border-orange-500/20" },
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

function isoDay(iso: string): string {
  // Interpreta como local para corresponder ao calendário
  const d = new Date(iso.replace("T", " ").substring(0, 16));
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
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
  const [confirmando, setConfirmando] = useState<string | null>(null);
  const [editando, setEditando] = useState<Intimacao | null>(null);
  const [diaSelecionado, setDiaSelecionado] = useState<string | null>(null);
  const [avisoSemInquerito, setAvisoSemInquerito] = useState<string | null>(null);
  const router = useRouter();

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

  // Polling: quando há intimações em processamento, recarrega a cada 5s
  useEffect(() => {
    const temProcessando = intimacoes.some((i) => i.status === "processando");
    if (!temProcessando) return;
    const interval = setInterval(carregar, 5000);
    return () => clearInterval(interval);
  }, [intimacoes]);

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

  const handleConfirmarAgenda = async (id: string) => {
    setConfirmando(id);
    try {
      await api.post(`/intimacoes/${id}/confirmar-agenda`);
      await carregar();
    } catch {
      alert("Erro ao criar evento no Google Agenda.");
    } finally {
      setConfirmando(null);
    }
  };

  const handleIgnorarDataPassada = async (id: string) => {
    setConfirmando(id);
    try {
      await api.post(`/intimacoes/${id}/ignorar-data-passada`);
      await carregar();
    } finally {
      setConfirmando(null);
    }
  };

  const handleSaved = (atualizada: Intimacao) => {
    setIntimacoes((prev) => prev.map((i) => (i.id === atualizada.id ? atualizada : i)));
  };

  // Filtra por dia selecionado no calendário
  const intimacoesFiltradas = diaSelecionado
    ? intimacoes.filter((i) => i.data_oitiva && isoDay(i.data_oitiva) === diaSelecionado)
    : intimacoes;

  const grupos = groupByMonth(intimacoesFiltradas);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
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

      {/* Calendário */}
      <div className="mb-6">
        <CalendarioIntimacoes
          intimacoes={intimacoes}
          diaSelecionado={diaSelecionado}
          onDiaClick={setDiaSelecionado}
        />
      </div>

      {/* Filtro ativo */}
      {diaSelecionado && (
        <div className="flex items-center gap-2 mb-4 text-sm">
          <span className="text-zinc-400">
            Mostrando:{" "}
            <span className="text-blue-400 font-medium">
              {new Date(diaSelecionado + "T12:00:00").toLocaleDateString("pt-BR", {
                weekday: "long", day: "2-digit", month: "long",
              })}
            </span>
          </span>
          <button
            onClick={() => setDiaSelecionado(null)}
            className="text-xs text-zinc-600 hover:text-zinc-400 underline transition-colors"
          >
            ver todas
          </button>
        </div>
      )}

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

      {!loading && !erro && intimacoesFiltradas.length === 0 && (
        <div className="text-center py-16 text-zinc-600">
          <Calendar size={40} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">
            {diaSelecionado ? "Nenhuma intimação neste dia." : "Nenhuma intimação lançada ainda."}
          </p>
          {!diaSelecionado && (
            <p className="text-xs mt-1">Clique em "Lançar Intimação" para começar.</p>
          )}
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
                  onDoubleClick={() => {
                    if (intim.inquerito_id) {
                      router.push(`/inqueritos/${intim.inquerito_id}?sintese=1`);
                    } else {
                      setAvisoSemInquerito(intim.id);
                      setTimeout(() => setAvisoSemInquerito(null), 4000);
                    }
                  }}
                  className={`border border-zinc-800 rounded-xl p-4 bg-zinc-900/40 hover:bg-zinc-900/70 transition-colors ${intim.inquerito_id ? "cursor-pointer" : ""}`}
                  title={intim.inquerito_id ? "Duplo clique para abrir inquérito e síntese" : undefined}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-2 flex-1 min-w-0">
                      {/* Nome + qualificação */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-zinc-100 flex items-center gap-1.5">
                          {intim.status === "processando" ? (
                            <Loader2 size={14} className="text-zinc-500 shrink-0 animate-spin" />
                          ) : (
                            <User size={14} className="text-zinc-500 shrink-0" />
                          )}
                          {intim.intimado_nome ?? (
                            intim.status === "processando"
                              ? <span className="text-zinc-600 italic">Extraindo dados...</span>
                              : <span className="text-zinc-500 italic">Nome não extraído</span>
                          )}
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

                      {/* Inquérito, data, local */}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
                        {intim.numero_inquerito_extraido && (
                          <span className="flex items-center gap-1 font-medium text-zinc-400">
                            <Hash size={11} className="shrink-0" />
                            IP {intim.numero_inquerito_extraido}
                          </span>
                        )}
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
                      </div>
                    </div>

                    {/* Ações */}
                    <div className="flex items-center gap-1 shrink-0">
                      {intim.status !== "processando" && (
                        <button
                          onClick={() => setEditando(intim)}
                          className="p-1.5 text-zinc-600 hover:text-blue-400 transition-colors"
                          title="Editar intimação"
                        >
                          <Pencil size={14} />
                        </button>
                      )}
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

                  {/* Aviso: sem inquérito vinculado */}
                  {avisoSemInquerito === intim.id && (
                    <div className="mt-3 flex items-center gap-2 rounded-lg bg-zinc-800/80 border border-zinc-700 px-3 py-2 text-xs text-zinc-400">
                      <AlertCircle size={13} className="shrink-0 text-zinc-500" />
                      Nenhum inquérito importado no sistema para esta intimação. Importe o procedimento em <span className="text-blue-400 mx-1">Inquéritos</span> para acessar a síntese investigativa.
                    </div>
                  )}

                  {/* Confirmação: data passada */}
                  {intim.status === "data_passada" && (
                    <div className="mt-3 flex items-center gap-3 rounded-lg bg-amber-500/10 border border-amber-500/20 px-3 py-2 text-xs text-amber-300">
                      <AlertCircle size={14} className="shrink-0" />
                      <span className="flex-1">A data da oitiva já passou. Deseja incluir no Google Agenda mesmo assim?</span>
                      <button
                        onClick={() => handleConfirmarAgenda(intim.id)}
                        disabled={confirmando === intim.id}
                        className="px-2 py-1 rounded bg-amber-500/20 hover:bg-amber-500/40 text-amber-200 font-medium transition-colors disabled:opacity-40 whitespace-nowrap"
                      >
                        {confirmando === intim.id ? <Loader2 size={12} className="animate-spin" /> : "Sim, agendar"}
                      </button>
                      <button
                        onClick={() => handleIgnorarDataPassada(intim.id)}
                        disabled={confirmando === intim.id}
                        className="px-2 py-1 rounded hover:bg-zinc-700/50 text-zinc-400 transition-colors disabled:opacity-40"
                      >
                        Ignorar
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Modais */}
      {showModal && (
        <IntimacaoUploadModal
          onClose={() => setShowModal(false)}
          onSuccess={() => {
            setShowModal(false);
            setTimeout(carregar, 2000);
          }}
        />
      )}

      {editando && (
        <IntimacaoEditModal
          intimacao={editando}
          onClose={() => setEditando(null)}
          onSaved={(atualizada) => {
            handleSaved(atualizada);
            setEditando(null);
          }}
        />
      )}
    </div>
  );
}
