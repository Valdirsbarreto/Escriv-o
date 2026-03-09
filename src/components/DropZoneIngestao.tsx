"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { CloudUpload, FileText, FileImage, Loader2, CheckCircle2, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiMultipart } from "@/lib/api";

type Stage =
  | "idle"
  | "uploading"
  | "analisando_ia"
  | "extraindo_dados"
  | "criando_inquerito"
  | "concluido"
  | "erro";

interface ArquivoItem {
  name: string;
  size: number;
  type: string;
}

interface ResultadoIngestao {
  id_sessao: string;
  mensagem: string;
  arquivos_recebidos: string[];
  inquerito_id?: string;
  numero?: string;
}

const STAGES_LABELS: Record<Stage, string> = {
  idle: "",
  uploading: "Enviando arquivos para o servidor...",
  analisando_ia: "🧠 IA Orquestradora lendo os documentos...",
  extraindo_dados: "🔍 Extraindo nomes, datas e dados do inquérito...",
  criando_inquerito: "📁 Criando o Inquérito e registrando personagens...",
  concluido: "✅ Inquérito criado com sucesso!",
  erro: "❌ Ocorreu um erro durante a ingestão.",
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function DropZoneIngestao() {
  const [stage, setStage] = useState<Stage>("idle");
  const [arquivos, setArquivos] = useState<ArquivoItem[]>([]);
  const [resultado, setResultado] = useState<ResultadoIngestao | null>(null);
  const [erro, setErro] = useState<string>("");

  const simularProgresso = (callback: () => void) => {
    // Simula progressão realista dos estágios de processamento
    setTimeout(() => setStage("analisando_ia"), 800);
    setTimeout(() => setStage("extraindo_dados"), 2500);
    setTimeout(() => setStage("criando_inquerito"), 4000);
    setTimeout(callback, 5500);
  };

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;

    setArquivos(acceptedFiles.map((f) => ({ name: f.name, size: f.size, type: f.type })));
    setStage("uploading");
    setErro("");
    setResultado(null);

    try {
      const formData = new FormData();
      acceptedFiles.forEach((file) => formData.append("files", file));

      const response = await apiMultipart.post("/ingestao/iniciar", formData);
      const data: ResultadoIngestao = response.data;

      simularProgresso(() => {
        setResultado(data);
        setStage("concluido");
      });
    } catch (err: any) {
      setStage("erro");
      setErro(err?.response?.data?.detail || err?.message || "Erro desconhecido.");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/tiff": [".tiff", ".tif"],
    },
    disabled: stage !== "idle" && stage !== "concluido" && stage !== "erro",
    multiple: true,
  });

  const resetar = () => {
    setStage("idle");
    setArquivos([]);
    setResultado(null);
    setErro("");
  };

  const isProcessing = ["uploading", "analisando_ia", "extraindo_dados", "criando_inquerito"].includes(stage);

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={cn(
          "relative border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-300 cursor-pointer group",
          isDragActive
            ? "border-blue-500 bg-blue-500/10 scale-[1.01]"
            : stage === "concluido"
            ? "border-green-500/60 bg-green-500/5"
            : stage === "erro"
            ? "border-red-500/60 bg-red-500/5"
            : isProcessing
            ? "border-amber-500/40 bg-amber-500/5 cursor-not-allowed"
            : "border-zinc-700 bg-zinc-900/50 hover:border-blue-500/50 hover:bg-blue-500/5"
        )}
      >
        <input {...getInputProps()} />

        {/* Icon / Animation */}
        <div className="flex flex-col items-center gap-4">
          {isProcessing ? (
            <div className="relative">
              <Loader2 className="w-14 h-14 text-amber-400 animate-spin" />
            </div>
          ) : stage === "concluido" ? (
            <CheckCircle2 className="w-14 h-14 text-green-400 animate-bounce" />
          ) : stage === "erro" ? (
            <AlertTriangle className="w-14 h-14 text-red-400" />
          ) : (
            <CloudUpload
              className={cn(
                "w-14 h-14 transition-transform duration-300",
                isDragActive ? "text-blue-400 scale-110" : "text-zinc-500 group-hover:text-blue-400 group-hover:scale-110"
              )}
            />
          )}

          {/* Text */}
          {stage === "idle" && (
            <>
              <div>
                <p className="text-xl font-semibold text-zinc-200">
                  {isDragActive ? "Solte os arquivos aqui!" : "Arraste os documentos do inquérito"}
                </p>
                <p className="text-zinc-500 text-sm mt-1">
                  PDF, PNG, JPG ou TIFF • O sistema criará o inquérito automaticamente
                </p>
              </div>
              <span className="text-xs text-zinc-600 bg-zinc-800 px-4 py-1.5 rounded-full">
                ou clique para selecionar arquivos
              </span>
            </>
          )}

          {isProcessing && (
            <div className="text-center animate-pulse">
              <p className="text-lg font-medium text-amber-300">{STAGES_LABELS[stage]}</p>
              <p className="text-zinc-500 text-sm mt-1">Isso pode levar alguns instantes...</p>
            </div>
          )}

          {stage === "concluido" && resultado && (
            <div className="text-center">
              <p className="text-lg font-semibold text-green-400">Ingestão Concluída!</p>
              <p className="text-zinc-300 text-sm mt-1">{resultado.mensagem}</p>
            </div>
          )}

          {stage === "erro" && (
            <div className="text-center">
              <p className="text-lg font-semibold text-red-400">Falha no envio</p>
              <p className="text-zinc-400 text-sm mt-1 max-w-md">{erro}</p>
            </div>
          )}
        </div>
      </div>

      {/* Lista de Arquivos */}
      {arquivos.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Arquivos enviados</p>
          {arquivos.map((f, i) => (
            <div key={i} className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5">
              {f.type?.startsWith("image") ? (
                <FileImage className="w-4 h-4 text-blue-400 shrink-0" />
              ) : (
                <FileText className="w-4 h-4 text-red-400 shrink-0" />
              )}
              <span className="text-sm text-zinc-300 flex-1 truncate">{f.name}</span>
              <span className="text-xs text-zinc-600">{formatBytes(f.size)}</span>
              {stage === "concluido" && <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />}
              {stage === "erro" && <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />}
            </div>
          ))}
        </div>
      )}

      {/* Ações pós-conclusão */}
      {(stage === "concluido" || stage === "erro") && (
        <div className="flex gap-3">
          <button
            onClick={resetar}
            className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-400 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors"
          >
            <X className="w-3.5 h-3.5" /> Enviar Outros Documentos
          </button>
          {stage === "concluido" && (
            <a
              href="/"
              className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors"
            >
              Ver Inquéritos
            </a>
          )}
        </div>
      )}
    </div>
  );
}
