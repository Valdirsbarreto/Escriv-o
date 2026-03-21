"use client";

import { useState, useRef } from "react";
import { Upload, X, CalendarPlus, FileText, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { apiMultipart } from "@/lib/api";

interface IntimacaoUploadModalProps {
  inquerito_id?: string;
  onClose: () => void;
  onSuccess?: () => void;
}

export function IntimacaoUploadModal({ inquerito_id, onClose, onSuccess }: IntimacaoUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [mensagem, setMensagem] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

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

  const handleSubmit = async () => {
    if (!file) return;
    setStatus("uploading");
    setMensagem("Enviando e processando...");

    const formData = new FormData();
    formData.append("file", file);

    const url = inquerito_id
      ? `/intimacoes/upload?inquerito_id=${inquerito_id}`
      : "/intimacoes/upload";

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

        {/* Body */}
        <div className="p-5 space-y-4">
          <p className="text-sm text-zinc-400">
            Envie o PDF ou foto da intimação. O sistema irá extrair os dados automaticamente e criar o evento no Google Agenda.
          </p>

          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`
              border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all
              ${dragging ? "border-blue-500 bg-blue-500/5" : "border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/40"}
              ${file ? "border-green-500/50 bg-green-500/5" : ""}
            `}
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
              disabled={!file || status === "uploading"}
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
