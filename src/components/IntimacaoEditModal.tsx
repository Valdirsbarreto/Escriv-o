"use client";

import { useState } from "react";
import { X, Pencil, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

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

interface IntimacaoEditModalProps {
  intimacao: Intimacao;
  onClose: () => void;
  onSaved: (atualizada: Intimacao) => void;
}

const QUALIFICACOES = [
  { value: "testemunha", label: "Testemunha" },
  { value: "investigado", label: "Investigado" },
  { value: "vitima", label: "Vítima" },
  { value: "perito", label: "Perito" },
  { value: "outro", label: "Outro" },
];

function isoToDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  // Remove o offset/Z e pega apenas YYYY-MM-DDTHH:MM
  return iso.replace("Z", "").replace("+00:00", "").substring(0, 16);
}

export function IntimacaoEditModal({ intimacao, onClose, onSaved }: IntimacaoEditModalProps) {
  const [form, setForm] = useState({
    intimado_nome: intimacao.intimado_nome ?? "",
    intimado_cpf: intimacao.intimado_cpf ?? "",
    intimado_qualificacao: intimacao.intimado_qualificacao ?? "outro",
    numero_inquerito_extraido: intimacao.numero_inquerito_extraido ?? "",
    data_oitiva: isoToDatetimeLocal(intimacao.data_oitiva),
    local_oitiva: intimacao.local_oitiva ?? "",
  });
  const [status, setStatus] = useState<"idle" | "salvando" | "ok" | "erro">("idle");
  const [erro, setErro] = useState("");

  const handleSave = async () => {
    if (!form.intimado_nome.trim()) {
      setErro("Nome é obrigatório.");
      setStatus("erro");
      return;
    }
    setStatus("salvando");
    setErro("");
    try {
      const payload: Record<string, unknown> = {
        intimado_nome: form.intimado_nome.trim() || null,
        intimado_cpf: form.intimado_cpf.trim() || null,
        intimado_qualificacao: form.intimado_qualificacao || null,
        numero_inquerito_extraido: form.numero_inquerito_extraido.trim() || null,
        local_oitiva: form.local_oitiva.trim() || null,
      };
      if (form.data_oitiva) {
        payload.data_oitiva = new Date(form.data_oitiva).toISOString();
      }
      const res = await api.patch(`/intimacoes/${intimacao.id}`, payload);
      setStatus("ok");
      setTimeout(() => {
        onSaved(res.data);
        onClose();
      }, 800);
    } catch (err: any) {
      setErro(err.response?.data?.detail ?? "Erro ao salvar.");
      setStatus("erro");
    }
  };

  const field = (label: string, node: React.ReactNode) => (
    <div>
      <label className="text-xs text-zinc-400 mb-1 block">{label}</label>
      {node}
    </div>
  );

  const input = (key: keyof typeof form, type = "text", placeholder = "") => (
    <input
      type={type}
      value={form[key]}
      onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
      placeholder={placeholder}
      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-blue-500"
    />
  );

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-md shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-2">
            <Pencil size={16} className="text-blue-400" />
            <span className="font-semibold text-zinc-100">Editar Intimação</span>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-3 overflow-y-auto flex-1">
          {field("Nome do Intimado *", input("intimado_nome", "text", "Nome completo"))}
          {field("CPF", input("intimado_cpf", "text", "000.000.000-00"))}
          {field(
            "Qualificação",
            <select
              value={form.intimado_qualificacao}
              onChange={(e) => setForm((f) => ({ ...f, intimado_qualificacao: e.target.value }))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500"
            >
              {QUALIFICACOES.map((q) => (
                <option key={q.value} value={q.value}>{q.label}</option>
              ))}
            </select>
          )}
          {field("Data e Hora da Oitiva", input("data_oitiva", "datetime-local"))}
          {field("Local", input("local_oitiva", "text", "Ex: 1ª DP — Sala de Oitivas"))}
          {field("Nº do Inquérito", input("numero_inquerito_extraido", "text", "Ex: 033-07699/2024"))}

          {status === "erro" && (
            <div className="flex items-center gap-2 text-sm bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg px-3 py-2">
              <AlertCircle size={14} className="shrink-0" />
              {erro}
            </div>
          )}
          {status === "ok" && (
            <div className="flex items-center gap-2 text-sm bg-green-500/10 border border-green-500/20 text-green-400 rounded-lg px-3 py-2">
              <CheckCircle2 size={14} className="shrink-0" />
              Salvo! Evento no Google Agenda atualizado.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-5 border-t border-zinc-800 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={status === "salvando" || status === "ok"}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-500 hover:bg-blue-400 text-white transition-colors disabled:opacity-40 flex items-center gap-2"
          >
            {status === "salvando" && <Loader2 size={14} className="animate-spin" />}
            {status === "salvando" ? "Salvando..." : "Salvar"}
          </button>
        </div>
      </div>
    </div>
  );
}
