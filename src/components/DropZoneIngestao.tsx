"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  CloudUpload, FileText, FileImage, Loader2,
  CheckCircle2, AlertTriangle, X, WifiOff, Brain, ArrowRight
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, apiMultipart, ingestaoIniciarUrl } from "@/lib/api";
import { OneDrivePicker } from "@/components/OneDrivePicker";

type Stage = "idle" | "uploading" | "analisando_ia" | "extraindo_dados" | "criando_inquerito" | "orquestrando" | "concluido" | "erro";

interface ArquivoItem { name: string; size: number; type: string; }

interface ResultadoIngestao {
  id_sessao: string;
  mensagem: string;
  arquivos_recebidos: string[];
}

interface LoteStatus { lote: number; total: number; concluido: boolean; erro?: string; }

const BATCH_SIZE = 10; // máximo de arquivos por lote
const MAX_FILES = 100;

const STAGES_LABELS: Record<Stage, string> = {
  idle: "",
  uploading: "Enviando arquivos para o servidor...",
  analisando_ia: "🧠 IA Orquestradora lendo os documentos...",
  extraindo_dados: "🔍 Extraindo nomes, datas e dados do inquérito...",
  criando_inquerito: "📁 Criando o Inquérito e registrando personagens...",
  orquestrando: "IA Orquestradora analisando os documentos...",
  concluido: "✅ Inquérito criado com sucesso!",
  erro: "❌ Falha no envio",
};

const ORQUESTRANDO_STEPS = [
  { label: "Lendo e extraindo texto dos documentos", done: false },
  { label: "Identificando número do IP e delegacia", done: false },
  { label: "Reconhecendo personagens e partes envolvidas", done: false },
  { label: "Criando inquérito e registrando no sistema", done: false },
  { label: "Gerando relatório investigativo inicial", done: false },
];

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function diagnosarErro(err: any): string {
  if (!err) return "Erro desconhecido.";
  
  // Sem resposta = backend inacessível
  if (err.code === "ERR_NETWORK" || !err.response) {
    const url = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    return `Não foi possível conectar ao backend (${url}).\n\nVerifique se o servidor FastAPI está rodando:\n  cd backend && uvicorn app.main:app --reload`;
  }
  
  if (err.response?.status === 413) return "Lote muito grande. Reduza o número de arquivos por vez.";
  if (err.response?.status === 422) return `Erro de validação: ${JSON.stringify(err.response.data?.detail)}`;
  if (err.response?.status === 500) return "Erro interno no servidor. Verifique os logs do backend.";
  
  return err?.response?.data?.detail || err?.message || "Erro desconhecido.";
}

export function DropZoneIngestao() {
  const [stage, setStage] = useState<Stage>("idle");
  const [arquivos, setArquivos] = useState<ArquivoItem[]>([]);
  const [lotes, setLotes] = useState<LoteStatus[]>([]);
  const [progresso, setProgresso] = useState(0); // 0-100
  const [resultado, setResultado] = useState<ResultadoIngestao | null>(null);
  const [erro, setErro] = useState<string>("");
  const [inqueritoCriado, setInqueritoCriado] = useState<{ id: string; numero: string } | null>(null);
  const [stepAtivo, setStepAtivo] = useState(0);
  const uploadTimestampRef = useRef<number>(0);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stepIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (stepIntervalRef.current) clearInterval(stepIntervalRef.current);
    };
  }, []);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    
    const arquivosLimitados = acceptedFiles.slice(0, MAX_FILES);
    setArquivos(arquivosLimitados.map((f) => ({ name: f.name, size: f.size, type: f.type })));
    setStage("uploading");
    setErro("");
    setResultado(null);
    setProgresso(0);
    setInqueritoCriado(null);
    uploadTimestampRef.current = Date.now();
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    if (stepIntervalRef.current) clearInterval(stepIntervalRef.current);

    // Divide em lotes
    const batches: File[][] = [];
    for (let i = 0; i < arquivosLimitados.length; i += BATCH_SIZE) {
      batches.push(arquivosLimitados.slice(i, i + BATCH_SIZE));
    }

    const statusLotes: LoteStatus[] = batches.map((_, i) => ({
      lote: i + 1,
      total: batches.length,
      concluido: false
    }));
    setLotes([...statusLotes]);

    let ultimoResultado: ResultadoIngestao | null = null;
    let algumErro = false;

    for (let i = 0; i < batches.length; i++) {
        const batch = batches[i];
        const baseProgresso = (i / batches.length) * 100;
        
        // Estágio visual progressivo baseado no lote
        if (i === 0) setStage("uploading");
        else if (i === Math.floor(batches.length * 0.4)) setStage("analisando_ia");
        else if (i === Math.floor(batches.length * 0.7)) setStage("extraindo_dados");
        else if (i === batches.length - 1) setStage("criando_inquerito");

        try {
            const formData = new FormData();
            batch.forEach((file) => formData.append("files", file));

            const response = await apiMultipart.post("/ingestao/iniciar", formData, {
                timeout: 120_000,
                onUploadProgress: (progressEvent) => {
                    if (progressEvent.total) {
                        const uploadPercent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                        const progressoReal = baseProgresso + (uploadPercent / batches.length);
                        setProgresso(Math.round(progressoReal));
                    }
                },
            });
            
            ultimoResultado = response.data;
            statusLotes[i] = { ...statusLotes[i], concluido: true };
        } catch (err: any) {
            const msg = diagnosarErro(err);
            statusLotes[i] = { ...statusLotes[i], concluido: false, erro: msg };
            
            if (err.code === "ERR_NETWORK" || !err.response) {
                setLotes([...statusLotes]);
                setStage("erro");
                setErro(msg);
                return;
            }
            algumErro = true;
        }

        setLotes([...statusLotes]);
        setProgresso(Math.round(((i + 1) / batches.length) * 100));
    }

    if (ultimoResultado && !algumErro) {
      setResultado(ultimoResultado);
      setStage("orquestrando");
      setStepAtivo(0);

      // Animar steps a cada 6s
      let stepIdx = 0;
      stepIntervalRef.current = setInterval(() => {
        stepIdx = Math.min(stepIdx + 1, ORQUESTRANDO_STEPS.length - 1);
        setStepAtivo(stepIdx);
      }, 6000);

      // Polling: detectar quando o inquérito aparecer
      const uploadTs = uploadTimestampRef.current;
      let pollCount = 0;
      pollIntervalRef.current = setInterval(async () => {
        pollCount++;
        if (pollCount > 40) {
          clearInterval(pollIntervalRef.current!);
          clearInterval(stepIntervalRef.current!);
          setStage("concluido");
          return;
        }
        try {
          const res = await api.get("/inqueritos");
          const items: any[] = res.data?.items ?? res.data ?? [];
          const novo = items.find((inq: any) =>
            new Date(inq.created_at).getTime() > uploadTs - 5000
          );
          if (novo) {
            clearInterval(pollIntervalRef.current!);
            clearInterval(stepIntervalRef.current!);
            setInqueritoCriado({ id: novo.id, numero: novo.numero });
            setStage("concluido");
          }
        } catch { /* ignora erro de rede no poll */ }
      }, 3000);
    } else if (algumErro) {
      setStage("erro");
      const errosMsg = statusLotes.filter((l) => l.erro).map((l) => `Lote ${l.lote}: ${l.erro}`).join("\n");
      setErro(errosMsg || "Alguns lotes falharam.");
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
    disabled: !["idle", "concluido", "erro"].includes(stage),
    multiple: true,
    maxFiles: MAX_FILES,
  });

  const resetar = () => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    if (stepIntervalRef.current) clearInterval(stepIntervalRef.current);
    setStage("idle"); setArquivos([]); setLotes([]); setResultado(null);
    setErro(""); setProgresso(0); setInqueritoCriado(null); setStepAtivo(0);
  };

  const handleOneDrive = async (file: { nome: string; downloadUrl: string }) => {
    setStage("uploading");
    setErro("");
    setResultado(null);
    setProgresso(0);
    setInqueritoCriado(null);
    setArquivos([{ name: file.nome, size: 0, type: "application/pdf" }]);
    uploadTimestampRef.current = Date.now();

    try {
      const res = await ingestaoIniciarUrl(file.downloadUrl, file.nome);
      setResultado({ id_sessao: res.id_sessao, mensagem: res.mensagem, arquivos_recebidos: res.arquivos_recebidos });
      setStage("orquestrando");
      setStepAtivo(0);

      let stepIdx = 0;
      stepIntervalRef.current = setInterval(() => {
        stepIdx = Math.min(stepIdx + 1, ORQUESTRANDO_STEPS.length - 1);
        setStepAtivo(stepIdx);
      }, 6000);

      const uploadTs = uploadTimestampRef.current;
      let pollCount = 0;
      pollIntervalRef.current = setInterval(async () => {
        pollCount++;
        if (pollCount > 40) { clearInterval(pollIntervalRef.current!); clearInterval(stepIntervalRef.current!); setStage("concluido"); return; }
        try {
          const r = await api.get("/inqueritos");
          const items: any[] = r.data?.items ?? r.data ?? [];
          const novo = items.find((inq: any) => new Date(inq.created_at).getTime() > uploadTs - 5000);
          if (novo) { clearInterval(pollIntervalRef.current!); clearInterval(stepIntervalRef.current!); setInqueritoCriado({ id: novo.id, numero: novo.numero }); setStage("concluido"); }
        } catch { /* ignora */ }
      }, 3000);
    } catch (e: any) {
      setStage("erro");
      setErro(e?.response?.data?.detail || e?.message || "Erro ao importar do OneDrive.");
    }
  };

  const isProcessing = ["uploading", "analisando_ia", "extraindo_dados", "criando_inquerito"].includes(stage);
  const isOrquestrando = stage === "orquestrando";
  const isNetworkError = erro.includes("conectar ao backend") || erro.includes("FastAPI");

  return (
    <div className="space-y-4">

      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={cn(
          "relative border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-300 cursor-pointer group",
          isDragActive ? "border-blue-500 bg-blue-500/10 scale-[1.01]"
            : stage === "concluido" ? "border-blue-500/60 bg-blue-500/5"
            : isOrquestrando ? "border-blue-500/40 bg-blue-500/5 cursor-not-allowed"
            : isNetworkError ? "border-orange-500/60 bg-orange-500/5"
            : stage === "erro" ? "border-red-500/60 bg-red-500/5"
            : isProcessing ? "border-amber-500/40 bg-amber-500/5 cursor-not-allowed"
            : "border-zinc-700 bg-zinc-900/50 hover:border-blue-500/50 hover:bg-blue-500/5"
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-4">
          {isProcessing ? (
            <Loader2 className="w-14 h-14 text-amber-400 animate-spin" />
          ) : isOrquestrando ? (
            <Brain className="w-14 h-14 text-blue-400 animate-pulse" />
          ) : stage === "concluido" ? (
            <Loader2 className="w-14 h-14 text-blue-400 animate-spin" />
          ) : isNetworkError ? (
            <WifiOff className="w-14 h-14 text-orange-400" />
          ) : stage === "erro" ? (
            <AlertTriangle className="w-14 h-14 text-red-400" />
          ) : (
            <CloudUpload className={cn("w-14 h-14 transition-transform duration-300",
              isDragActive ? "text-blue-400 scale-110" : "text-zinc-500 group-hover:text-blue-400 group-hover:scale-110"
            )} />
          )}

          {stage === "idle" && (
            <>
              <div>
                <p className="text-xl font-semibold text-zinc-200">
                  {isDragActive ? "Solte os arquivos aqui!" : "Arraste os documentos do inquérito"}
                </p>
                <p className="text-zinc-500 text-sm mt-1">
                  PDF, PNG, JPG ou TIFF • Até {MAX_FILES} arquivos • Enviados em lotes de {BATCH_SIZE}
                </p>
              </div>
              <span className="text-xs text-zinc-600 bg-zinc-800 px-4 py-1.5 rounded-full">
                ou clique para selecionar arquivos
              </span>
            </>
          )}

          {isProcessing && (
            <div className="text-center w-full max-w-sm">
              <p className="text-lg font-medium text-amber-300 animate-pulse">{STAGES_LABELS[stage]}</p>
              {/* Barra de Progresso */}
              <div className="mt-3 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-400 rounded-full transition-all duration-500"
                  style={{ width: `${progresso}%` }}
                />
              </div>
              <p className="text-zinc-600 text-xs mt-1">{progresso}% completo</p>
            </div>
          )}

          {isOrquestrando && (
            <div className="text-center w-full max-w-sm">
              <p className="text-lg font-semibold text-blue-300 animate-pulse">IA Orquestradora trabalhando...</p>
              <p className="text-zinc-500 text-xs mt-1 mb-4">Analisando documentos em segundo plano</p>
              <div className="space-y-2 text-left">
                {ORQUESTRANDO_STEPS.map((step, i) => (
                  <div key={i} className={cn(
                    "flex items-center gap-2 text-xs transition-all duration-500",
                    i < stepAtivo ? "text-green-400" : i === stepAtivo ? "text-blue-300" : "text-zinc-600"
                  )}>
                    {i < stepAtivo ? (
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    ) : i === stepAtivo ? (
                      <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin" />
                    ) : (
                      <div className="w-3.5 h-3.5 rounded-full border border-zinc-700 shrink-0" />
                    )}
                    {step.label}
                  </div>
                ))}
              </div>
            </div>
          )}

          {stage === "concluido" && (
            <div className="text-center">
              <p className="text-lg font-semibold text-blue-400">
                {inqueritoCriado ? `IP Nº ${inqueritoCriado.numero} criado` : "Ingestão recebida"}
              </p>
              <p className="text-zinc-400 text-sm mt-1">
                Documentos sendo processados em segundo plano — pode levar alguns minutos
              </p>
            </div>
          )}

          {stage === "erro" && (
            <div className="text-center max-w-md">
              <p className="text-lg font-semibold text-red-400">
                {isNetworkError ? "Backend não encontrado" : "Falha no envio"}
              </p>
              <pre className="text-zinc-400 text-xs mt-2 whitespace-pre-wrap text-left bg-black/30 rounded-lg p-3">
                {erro}
              </pre>
            </div>
          )}
        </div>
      </div>

      {/* Botão OneDrive — só aparece quando idle */}
      {stage === "idle" && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-600">ou importe direto do</span>
          <OneDrivePicker onFileSelected={handleOneDrive} />
        </div>
      )}

      {/* Progresso de Lotes */}
      {lotes.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">
            Lotes ({lotes.filter((l) => l.concluido).length}/{lotes.length} enviados)
          </p>
          <div className="flex flex-wrap gap-2">
            {lotes.map((l, i) => (
              <div
                key={i}
                title={l.erro || `Lote ${l.lote}`}
                className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold transition-all",
                  l.concluido ? "bg-green-500/20 text-green-400 border border-green-500/40"
                    : l.erro ? "bg-red-500/20 text-red-400 border border-red-500/40"
                    : "bg-zinc-800 text-zinc-500 border border-zinc-700"
                )}
              >
                {l.lote}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Lista de Arquivos */}
      {arquivos.length > 0 && (
        <details className="group">
          <summary className="text-xs font-semibold text-zinc-500 uppercase tracking-widest cursor-pointer hover:text-zinc-300 transition-colors">
            Arquivos ({arquivos.length}) ▾
          </summary>
          <div className="mt-2 space-y-1.5 max-h-64 overflow-y-auto pr-1">
            {arquivos.map((f, i) => (
              <div key={i} className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2">
                {f.type?.startsWith("image") ? (
                  <FileImage className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                ) : (
                  <FileText className="w-3.5 h-3.5 text-red-400 shrink-0" />
                )}
                <span className="text-xs text-zinc-300 flex-1 truncate">{f.name}</span>
                <span className="text-xs text-zinc-600 shrink-0">{formatBytes(f.size)}</span>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Ações pós-conclusão */}
      {["concluido", "erro", "orquestrando"].includes(stage) && (
        <div className="flex gap-3 flex-wrap">
          <button
            onClick={resetar}
            className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-400 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors"
          >
            <X className="w-3.5 h-3.5" /> Enviar Outros Arquivos
          </button>
          {stage === "concluido" && inqueritoCriado && (
            <a
              href={`/inqueritos/${inqueritoCriado.id}`}
              className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-700 hover:bg-blue-600 rounded-lg transition-colors"
            >
              <ArrowRight className="w-3.5 h-3.5" /> Acompanhar Processamento
            </a>
          )}
          {(stage === "concluido" || stage === "orquestrando") && (
            <a
              href="/"
              className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors"
            >
              Ver Todos os Inquéritos
            </a>
          )}
        </div>
      )}
    </div>
  );
}
