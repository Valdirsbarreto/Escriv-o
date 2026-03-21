"use client";

import { useState, useRef } from "react";
import { Upload, X, CalendarPlus, FileText, Loader2, CheckCircle2, AlertCircle, Keyboard } from "lucide-react";
import { api, apiMultipart } from "@/lib/api";

interface IntimacaoUploadModalProps {
  inquerito_id?: string;
  onClose: () => void;
  onSuccess?: () => void;
}

type Aba = "upload" | "manual";

const QUALIFICACOES = [
  { value: "testemunha", label: "Testemunha" },
  { value: "investigado", label: "Investigado" },
  { value: "vitima", label: "Vítima" },
  { value: "perito", label: "Perito" },
  { value: "outro", label: "Outro" },
];

export function IntimacaoUploadModal({ inquerito_id, onClose, onSuccess }: IntimacaoUploadModalProps) {
  const [aba, setAba] = useState<Aba>("upload");

  // ── Upload ──────────────────────────────────────────────
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Manual ──────────────────────────────────────────────
  const [form, setForm] = useState({
    intimado_nome: "",
    intimado_qualificacao: "testemunha",
    numero_inquerito: inquerito_id ? "" : "",
    data_oitiva: "",
    local_oitiva: "",
  });

  // ── Shared ──────────────────────────────────────────────
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [mensagem, setMensagem] = useState("");

  // ── Upload handlers ─────────────────────────────────────
  const handleFile = (f: File) => {
    const ext = f.name.toLowerCase().split(".").pop();
    if (!["pdf", "png", "jpg", "jpeg", "tiff"].includes(ext ?? "")) {
      setMensagem("Formato não suportado. Use PDF, PNG, JPG ou TIFF.");
      setStatus("error");
      return;
    }
    setFile(f);
    setStatus("idle");
    setMensagem("");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleSubmitUpload = async () => {
    if (!file) return;
    setStatus("uploading");
    setMensagem("Enviando e processando...");
    const formData = new FormData();
    formData.append("file", file);
    const url = inquerito_id ? `/intimacoes/upload?inquerito_id=${inquerito_id}` : "/intimacoes/upload";
    try {
      await apiMultipart.post(url, formData);
      setStatus("success");
      setMensagem("Intimação recebida! Os dados estão sendo extraídos e o evento será criado no Google Agenda em instantes.");
      onSuccess?.();
    } catch (err: any) {
      setStatus("error");
      setMensagem(err.response?.data?.detail ?? "Erro ao enviar. Tente novamente.");
    }
  };

  // ── Manual handler ───────────────────────────────────────
  const handleSubmitManual = async () => {
    if (!form.intimado_nome.trim()) {
      setMensagem("Nome do intimado é obrigatório.");
      setStatus("error");
      return;
    }
    if (!form.data_oitiva) {
      setMensagem("Data e hora da oitiva são obrigatórias.");
      setStatus("error");
      return;
    }
    setStatus("uploading");
    setMensagem("Criando evento no Google Agenda...");
    try {
      await api.post("/intimacoes/manual", {
        intimado_nome: form.intimado_nome.trim(),
        intimado_qualificacao: form.intimado_qualificacao,
        numero_inquerito_extraido: form.numero_inquerito.trim() || null,
        data_oitiva: new Date(form.data_oitiva).toISOString(),
        local_oitiva: form.local_oitiva.trim() || null,
        inquerito_id: inquerito_id ?? null,
      });
      setStatus("success");
      setMensagem("Intimação lançada! Evento criado no Google Agenda.");
      onSuccess?.();
    } catch (err: any) {
      setStatus("error");
      setMensagem(err.response?.data?.detail ?? "Erro ao criar. Tente novamente.");
    }
  };

  const handleSubmit = aba === "upload" ? handleSubmitUpload : handleSubmitManual;
  const submitDisabled =
    status === "uploading" ||
    (aba === "upload" && !file) ||
    (aba === "manual" && (!form.intimado_nome.trim() || !form.data_oitiva));

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-md shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <CalendarPlus size={18} className="text-blue-400" />
            <span className="font-semibold text-zinc-100">Lançar Intimação na Agenda</span>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-zinc-800">
          <button
            onClick={() => { setAba("upload"); setStatus("idle"); setMensagem(""); }}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              aba === "upload"
                ? "text-blue-400 border-b-2 border-blue-400 -mb-px"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <Upload size={14} /> Enviar PDF / Foto
          </button>
          <button
            onClick={() => { setAba("manual"); setStatus("idle"); setMensagem(""); }}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              aba === "manual"
                ? "text-blue-400 border-b-2 border-blue-400 -mb-px"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <Keyboard size={14} /> Lançar Manualmente
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {aba === "upload" && (
            <>
              <p className="text-sm text-zinc-400">
                Envie o PDF ou foto da intimação. Os dados serão extraídos automaticamente.
              </p>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                  dragging ? "border-blue-500 bg-blue-500/5" :
                  file ? "border-green-500/50 bg-green-500/5" :
                  "border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/40"
                }`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.tiff"
                  className="hidden"
                  onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }}
                />
                {file ? (
                  <div className="flex flex-col items-center gap-2">
                    <FileText size={32} className="text-green-400" />
                    <span className="text-sm text-zinc-200 font-medium">{file.name}</span>
                    <span className="text-xs text-zinc-500">{(file.size / 1024).toFixed(0)} KB</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Upload size={32} className="text-zinc-600" />
                    <span className="text-sm text-zinc-400">Arraste ou clique para selecionar</span>
                    <span className="text-xs text-zinc-600">PDF, PNG, JPG ou TIFF</span>
                  </div>
                )}
              </div>
            </>
          )}

          {aba === "manual" && (
            <div className="space-y-3">
              {/* Nome */}
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Nome do Intimado *</label>
                <input
                  type="text"
                  value={form.intimado_nome}
                  onChange={(e) => setForm((f) => ({ ...f, intimado_nome: e.target.value }))}
                  placeholder="Nome completo"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Qualificação */}
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Qualificação</label>
                <select
                  value={form.intimado_qualificacao}
                  onChange={(e) => setForm((f) => ({ ...f, intimado_qualificacao: e.target.value }))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500"
                >
                  {QUALIFICACOES.map((q) => (
                    <option key={q.value} value={q.value}>{q.label}</option>
                  ))}
                </select>
              </div>

              {/* Data e hora */}
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Data e Hora da Oitiva *</label>
                <input
                  type="datetime-local"
                  value={form.data_oitiva}
                  onChange={(e) => setForm((f) => ({ ...f, data_oitiva: e.target.value }))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Local */}
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Local</label>
                <input
                  type="text"
                  value={form.local_oitiva}
                  onChange={(e) => setForm((f) => ({ ...f, local_oitiva: e.target.value }))}
                  placeholder="Ex: 1ª DP — Sala de Oitivas"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Nº Inquérito */}
              {!inquerito_id && (
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">Nº do Inquérito</label>
                  <input
                    type="text"
                    value={form.numero_inquerito}
                    onChange={(e) => setForm((f) => ({ ...f, numero_inquerito: e.target.value }))}
                    placeholder="Ex: 033-07699/2024"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-blue-500"
                  />
                </div>
              )}
            </div>
          )}

          {/* Feedback */}
          {mensagem && (
            <div className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2 ${
              status === "error" ? "bg-red-500/10 text-red-400 border border-red-500/20" :
              status === "success" ? "bg-green-500/10 text-green-400 border border-green-500/20" :
              "bg-blue-500/10 text-blue-400 border border-blue-500/20"
            }`}>
              {status === "error" && <AlertCircle size={15} className="mt-0.5 shrink-0" />}
              {status === "success" && <CheckCircle2 size={15} className="mt-0.5 shrink-0" />}
              {status === "uploading" && <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin" />}
              <span>{mensagem}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-5 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            {status === "success" ? "Fechar" : "Cancelar"}
          </button>
          {status !== "success" && (
            <button
              onClick={handleSubmit}
              disabled={submitDisabled}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-500 hover:bg-blue-400 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {status === "uploading" && <Loader2 size={14} className="animate-spin" />}
              {status === "uploading" ? "Processando..." : "Lançar na Agenda"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
