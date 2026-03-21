"use client";

import { useState, useRef } from "react";
import { Upload, X, CalendarPlus, FileText, Loader2, CheckCircle2, AlertCircle, Keyboard, Trash2 } from "lucide-react";
import { api, apiMultipart } from "@/lib/api";

interface IntimacaoUploadModalProps {
  inquerito_id?: string;
  onClose: () => void;
  onSuccess?: () => void;
}

type Aba = "upload" | "manual";

interface FileStatus {
  file: File;
  status: "pendente" | "enviando" | "ok" | "erro";
  mensagem?: string;
}

const QUALIFICACOES = [
  { value: "testemunha", label: "Testemunha" },
  { value: "investigado", label: "Investigado" },
  { value: "vitima", label: "Vítima" },
  { value: "perito", label: "Perito" },
  { value: "outro", label: "Outro" },
];

export function IntimacaoUploadModal({ inquerito_id, onClose, onSuccess }: IntimacaoUploadModalProps) {
  const [aba, setAba] = useState<Aba>("upload");

  // ── Upload (múltiplos arquivos) ──────────────────────────
  const [arquivos, setArquivos] = useState<FileStatus[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Manual ──────────────────────────────────────────────
  const [form, setForm] = useState({
    intimado_nome: "",
    intimado_qualificacao: "testemunha",
    numero_inquerito: "",
    data_oitiva: "",
    local_oitiva: "",
  });

  // ── Shared ──────────────────────────────────────────────
  const [globalStatus, setGlobalStatus] = useState<"idle" | "enviando" | "concluido" | "erro">("idle");
  const [mensagemManual, setMensagemManual] = useState("");
  const [statusManual, setStatusManual] = useState<"idle" | "uploading" | "success" | "error">("idle");

  // ── Upload handlers ─────────────────────────────────────
  const addFiles = (files: FileList | File[]) => {
    const novos: FileStatus[] = [];
    Array.from(files).forEach((f) => {
      const ext = f.name.toLowerCase().split(".").pop();
      if (!["pdf", "png", "jpg", "jpeg", "tiff"].includes(ext ?? "")) return;
      // evita duplicata por nome
      if (arquivos.some((a) => a.file.name === f.name)) return;
      novos.push({ file: f, status: "pendente" });
    });
    setArquivos((prev) => [...prev, ...novos]);
  };

  const removeFile = (idx: number) => {
    setArquivos((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  };

  const handleSubmitUpload = async () => {
    if (arquivos.length === 0) return;
    setGlobalStatus("enviando");

    const url = inquerito_id
      ? `/intimacoes/upload?inquerito_id=${inquerito_id}`
      : "/intimacoes/upload";

    let algumErro = false;

    for (let i = 0; i < arquivos.length; i++) {
      if (arquivos[i].status === "ok") continue; // já enviado

      setArquivos((prev) =>
        prev.map((a, idx) => (idx === i ? { ...a, status: "enviando" } : a))
      );

      const formData = new FormData();
      formData.append("file", arquivos[i].file);

      try {
        await apiMultipart.post(url, formData);
        setArquivos((prev) =>
          prev.map((a, idx) => (idx === i ? { ...a, status: "ok" } : a))
        );
      } catch (err: any) {
        algumErro = true;
        const msg = err.response?.data?.detail ?? "Erro ao enviar";
        setArquivos((prev) =>
          prev.map((a, idx) => (idx === i ? { ...a, status: "erro", mensagem: msg } : a))
        );
      }
    }

    setGlobalStatus(algumErro ? "erro" : "concluido");
    if (!algumErro) onSuccess?.();
  };

  // ── Manual handler ───────────────────────────────────────
  const handleSubmitManual = async () => {
    if (!form.intimado_nome.trim()) {
      setMensagemManual("Nome do intimado é obrigatório.");
      setStatusManual("error");
      return;
    }
    if (!form.data_oitiva) {
      setMensagemManual("Data e hora da oitiva são obrigatórias.");
      setStatusManual("error");
      return;
    }
    setStatusManual("uploading");
    setMensagemManual("Criando evento no Google Agenda...");
    try {
      await api.post("/intimacoes/manual", {
        intimado_nome: form.intimado_nome.trim(),
        intimado_qualificacao: form.intimado_qualificacao,
        numero_inquerito_extraido: form.numero_inquerito.trim() || null,
        data_oitiva: new Date(form.data_oitiva).toISOString(),
        local_oitiva: form.local_oitiva.trim() || null,
        inquerito_id: inquerito_id ?? null,
      });
      setStatusManual("success");
      setMensagemManual("Intimação lançada! Evento criado no Google Agenda.");
      onSuccess?.();
    } catch (err: any) {
      setStatusManual("error");
      setMensagemManual(err.response?.data?.detail ?? "Erro ao criar. Tente novamente.");
    }
  };

  const totalOk = arquivos.filter((a) => a.status === "ok").length;
  const totalErro = arquivos.filter((a) => a.status === "erro").length;
  const enviando = arquivos.some((a) => a.status === "enviando");

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-md shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-2">
            <CalendarPlus size={18} className="text-blue-400" />
            <span className="font-semibold text-zinc-100">Lançar Intimação na Agenda</span>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-zinc-800 shrink-0">
          <button
            onClick={() => { setAba("upload"); setGlobalStatus("idle"); }}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              aba === "upload"
                ? "text-blue-400 border-b-2 border-blue-400 -mb-px"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <Upload size={14} /> Enviar PDF / Foto
          </button>
          <button
            onClick={() => { setAba("manual"); setStatusManual("idle"); setMensagemManual(""); }}
            className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
              aba === "manual"
                ? "text-blue-400 border-b-2 border-blue-400 -mb-px"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <Keyboard size={14} /> Lançar Manualmente
          </button>
        </div>

        {/* Body — scrollável */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          {aba === "upload" && (
            <>
              {/* Drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                  dragging
                    ? "border-blue-500 bg-blue-500/5"
                    : "border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/40"
                }`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.tiff"
                  multiple
                  className="hidden"
                  onChange={(e) => { if (e.target.files) addFiles(e.target.files); }}
                />
                <div className="flex flex-col items-center gap-2">
                  <Upload size={28} className="text-zinc-600" />
                  <span className="text-sm text-zinc-400">
                    Arraste ou clique para selecionar
                  </span>
                  <span className="text-xs text-zinc-600">
                    PDF, PNG, JPG ou TIFF · múltiplos arquivos permitidos
                  </span>
                </div>
              </div>

              {/* Lista de arquivos */}
              {arquivos.length > 0 && (
                <div className="space-y-2">
                  {arquivos.map((a, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg border text-sm transition-colors ${
                        a.status === "ok"
                          ? "border-green-500/20 bg-green-500/5"
                          : a.status === "erro"
                          ? "border-red-500/20 bg-red-500/5"
                          : a.status === "enviando"
                          ? "border-blue-500/20 bg-blue-500/5"
                          : "border-zinc-800 bg-zinc-800/40"
                      }`}
                    >
                      {/* Ícone de status */}
                      <div className="shrink-0">
                        {a.status === "ok" && <CheckCircle2 size={15} className="text-green-400" />}
                        {a.status === "erro" && <AlertCircle size={15} className="text-red-400" />}
                        {a.status === "enviando" && <Loader2 size={15} className="text-blue-400 animate-spin" />}
                        {a.status === "pendente" && <FileText size={15} className="text-zinc-500" />}
                      </div>

                      {/* Nome */}
                      <div className="flex-1 min-w-0">
                        <p className="truncate text-zinc-200">{a.file.name}</p>
                        {a.mensagem && (
                          <p className="text-xs text-red-400 truncate">{a.mensagem}</p>
                        )}
                      </div>

                      {/* Tamanho + remover */}
                      <span className="text-xs text-zinc-600 shrink-0">
                        {(a.file.size / 1024).toFixed(0)} KB
                      </span>
                      {a.status === "pendente" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                          className="text-zinc-600 hover:text-red-400 transition-colors shrink-0"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Resumo pós-envio */}
              {globalStatus === "concluido" && (
                <div className="flex items-center gap-2 text-sm bg-green-500/10 border border-green-500/20 text-green-400 rounded-lg px-3 py-2">
                  <CheckCircle2 size={15} className="shrink-0" />
                  {totalOk} intimação(ões) recebida(s)! Os eventos serão criados no Google Agenda em instantes.
                </div>
              )}
              {globalStatus === "erro" && totalOk > 0 && (
                <div className="flex items-center gap-2 text-sm bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 rounded-lg px-3 py-2">
                  <AlertCircle size={15} className="shrink-0" />
                  {totalOk} enviada(s) com sucesso, {totalErro} com erro. Corrija e reenvie.
                </div>
              )}
            </>
          )}

          {aba === "manual" && (
            <div className="space-y-3">
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
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Data e Hora da Oitiva *</label>
                <input
                  type="datetime-local"
                  value={form.data_oitiva}
                  onChange={(e) => setForm((f) => ({ ...f, data_oitiva: e.target.value }))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500"
                />
              </div>
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

              {mensagemManual && (
                <div className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2 ${
                  statusManual === "error" ? "bg-red-500/10 text-red-400 border border-red-500/20" :
                  statusManual === "success" ? "bg-green-500/10 text-green-400 border border-green-500/20" :
                  "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                }`}>
                  {statusManual === "error" && <AlertCircle size={15} className="mt-0.5 shrink-0" />}
                  {statusManual === "success" && <CheckCircle2 size={15} className="mt-0.5 shrink-0" />}
                  {statusManual === "uploading" && <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin" />}
                  <span>{mensagemManual}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-between items-center gap-3 p-5 border-t border-zinc-800 shrink-0">
          {aba === "upload" && arquivos.length > 0 && globalStatus === "idle" && (
            <span className="text-xs text-zinc-500">{arquivos.length} arquivo(s) selecionado(s)</span>
          )}
          {aba === "upload" && globalStatus === "concluido" && (
            <span className="text-xs text-green-400">{totalOk}/{arquivos.length} enviados</span>
          )}
          {aba !== "upload" && <span />}

          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              {globalStatus === "concluido" || statusManual === "success" ? "Fechar" : "Cancelar"}
            </button>

            {aba === "upload" && globalStatus !== "concluido" && (
              <button
                onClick={handleSubmitUpload}
                disabled={arquivos.length === 0 || enviando}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-500 hover:bg-blue-400 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {enviando && <Loader2 size={14} className="animate-spin" />}
                {enviando
                  ? `Enviando ${arquivos.findIndex((a) => a.status === "enviando") + 1}/${arquivos.length}...`
                  : `Lançar ${arquivos.length > 1 ? `${arquivos.length} Intimações` : "na Agenda"}`}
              </button>
            )}

            {aba === "manual" && statusManual !== "success" && (
              <button
                onClick={handleSubmitManual}
                disabled={!form.intimado_nome.trim() || !form.data_oitiva || statusManual === "uploading"}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-500 hover:bg-blue-400 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {statusManual === "uploading" && <Loader2 size={14} className="animate-spin" />}
                {statusManual === "uploading" ? "Criando..." : "Lançar na Agenda"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
