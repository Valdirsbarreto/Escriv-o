"use client";

import { useState, useRef, useCallback } from "react";
import { Mic, MicOff, FileText, Download, RotateCcw, CheckCircle, Clock, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { transcreverOitiva, lavrarTermo } from "@/lib/api";
import { useAppStore } from "@/store/app";

type Fase = "idle" | "gravando" | "processando" | "transcricao" | "lavrando" | "pronto";

export default function OitivaPage() {
  const [fase, setFase] = useState<Fase>("idle");
  const [duracao, setDuracao] = useState(0);
  const [transcricao, setTranscricao] = useState("");
  const [termo, setTermo] = useState("");
  const [erro, setErro] = useState("");

  // Dados do ato
  const [local, setLocal] = useState("");
  const [comissario, setComissario] = useState("");
  const [qualificacao, setQualificacao] = useState("");
  const [papel, setPapel] = useState("testemunha");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { inqueritoAtivoId } = useAppStore();

  const formatarDuracao = (s: number) => {
    const m = Math.floor(s / 60).toString().padStart(2, "0");
    const sec = (s % 60).toString().padStart(2, "0");
    return `${m}:${sec}`;
  };

  const iniciarGravacao = useCallback(async () => {
    setErro("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.start(1000); // chunk a cada 1s
      mediaRecorderRef.current = mr;
      setFase("gravando");
      setDuracao(0);
      timerRef.current = setInterval(() => setDuracao(d => d + 1), 1000);
    } catch (e: any) {
      setErro("Não foi possível acessar o microfone: " + e.message);
    }
  }, []);

  const pararGravacao = useCallback(() => {
    const mr = mediaRecorderRef.current;
    if (!mr) return;
    if (timerRef.current) clearInterval(timerRef.current);
    mr.stop();
    mr.stream.getTracks().forEach(t => t.stop());
    mediaRecorderRef.current = null;
    setFase("processando");

    // Aguarda onstop (dispara após stop())
    mr.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      try {
        const r = await transcreverOitiva(blob, "oitiva.webm");
        setTranscricao(r.transcricao);
        setFase("transcricao");
      } catch (e: any) {
        setErro("Erro na transcrição: " + (e?.response?.data?.detail || e.message));
        setFase("idle");
      }
    };
  }, []);

  const lavrar = useCallback(async () => {
    setFase("lavrando");
    setErro("");
    try {
      const agora = new Date();
      const dataHora = agora.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" })
        + " às " + agora.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
      const r = await lavrarTermo({
        transcricao,
        data_hora: dataHora,
        local,
        comissario,
        qualificacao,
        papel,
      });
      setTermo(r.termo);
      setFase("pronto");
    } catch (e: any) {
      setErro("Erro ao lavrar termo: " + (e?.response?.data?.detail || e.message));
      setFase("transcricao");
    }
  }, [transcricao, local, comissario, qualificacao, papel]);

  const exportar = () => {
    const blob = new Blob([termo], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "termo_de_oitiva.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const reiniciar = () => {
    setFase("idle");
    setTranscricao("");
    setTermo("");
    setErro("");
    setDuracao(0);
  };

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="border-b border-zinc-800 pb-4">
        <h1 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
          <Mic size={20} className="text-red-400" />
          Modo Oitiva
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Grave a oitiva e o sistema lavra o termo no padrão da Polícia Civil.
        </p>
      </div>

      {/* Erro */}
      {erro && (
        <div className="rounded-lg bg-red-900/20 border border-red-700/40 p-3 text-sm text-red-300">
          {erro}
        </div>
      )}

      {/* FASE: IDLE ou GRAVANDO */}
      {(fase === "idle" || fase === "gravando") && (
        <div className="space-y-4">
          {/* Dados do ato */}
          {fase === "idle" && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
              <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Dados do Ato (opcional)</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">Local</label>
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="ex: DDEF / 1ª DP"
                    value={local}
                    onChange={e => setLocal(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">Comissário</label>
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="Nome do Comissário"
                    value={comissario}
                    onChange={e => setComissario(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">Papel do declarante</label>
                  <select
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={papel}
                    onChange={e => setPapel(e.target.value)}
                  >
                    <option value="testemunha">Testemunha</option>
                    <option value="vítima">Vítima</option>
                    <option value="investigado">Investigado</option>
                    <option value="informante">Informante</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-zinc-400 mb-1 block">Qualificação breve</label>
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="Nome completo, CPF..."
                    value={qualificacao}
                    onChange={e => setQualificacao(e.target.value)}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Botão principal */}
          <div className="flex flex-col items-center gap-4 py-6">
            {fase === "idle" ? (
              <button
                onClick={iniciarGravacao}
                className="w-24 h-24 rounded-full bg-red-600 hover:bg-red-500 active:scale-95 transition-all flex items-center justify-center shadow-lg shadow-red-900/40"
              >
                <Mic size={36} className="text-white" />
              </button>
            ) : (
              <>
                <div className="relative">
                  <button
                    onClick={pararGravacao}
                    className="w-24 h-24 rounded-full bg-red-600 hover:bg-red-500 active:scale-95 transition-all flex items-center justify-center shadow-lg shadow-red-900/40"
                  >
                    <MicOff size={36} className="text-white" />
                  </button>
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-400 animate-ping" />
                </div>
                <div className="flex items-center gap-2 text-zinc-300">
                  <Clock size={14} className="text-red-400" />
                  <span className="font-mono text-lg">{formatarDuracao(duracao)}</span>
                  <span className="text-xs text-zinc-500">gravando...</span>
                </div>
              </>
            )}
            <p className="text-sm text-zinc-500">
              {fase === "idle" ? "Clique para iniciar a gravação" : "Clique para parar e processar"}
            </p>
          </div>
        </div>
      )}

      {/* FASE: PROCESSANDO */}
      {fase === "processando" && (
        <div className="flex flex-col items-center gap-3 py-12">
          <Loader2 size={32} className="text-blue-400 animate-spin" />
          <p className="text-zinc-400">Transcrevendo o áudio com Gemini...</p>
          <p className="text-xs text-zinc-600">Isso pode levar alguns segundos para gravações longas.</p>
        </div>
      )}

      {/* FASE: TRANSCRIÇÃO — revisar e lavrar */}
      {fase === "transcricao" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-zinc-300">Transcrição bruta</span>
              <span className="text-xs text-zinc-600">{transcricao.length} chars</span>
            </div>
            <textarea
              className="w-full bg-zinc-800/50 border border-zinc-700 rounded-md p-3 text-sm text-zinc-300 leading-relaxed focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
              rows={12}
              value={transcricao}
              onChange={e => setTranscricao(e.target.value)}
            />
            <p className="text-xs text-zinc-600 mt-1">Você pode corrigir a transcrição antes de lavrar.</p>
          </div>
          <div className="flex gap-3">
            <Button onClick={lavrar} className="flex-1 bg-blue-600 hover:bg-blue-500">
              <FileText size={15} className="mr-2" />
              Lavrar Termo de Oitiva
            </Button>
            <Button variant="outline" onClick={reiniciar} className="border-zinc-700 text-zinc-400 hover:text-zinc-200">
              <RotateCcw size={15} />
            </Button>
          </div>
        </div>
      )}

      {/* FASE: LAVRANDO */}
      {fase === "lavrando" && (
        <div className="flex flex-col items-center gap-3 py-12">
          <Loader2 size={32} className="text-blue-400 animate-spin" />
          <p className="text-zinc-400">Lavrando o termo no padrão formal...</p>
        </div>
      )}

      {/* FASE: PRONTO */}
      {fase === "pronto" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-green-400">
            <CheckCircle size={18} />
            <span className="text-sm font-semibold">Termo lavrado com sucesso</span>
          </div>
          <div className="rounded-lg border border-zinc-700 bg-zinc-900/50 p-4">
            <pre className="text-sm text-zinc-300 whitespace-pre-wrap leading-relaxed font-mono">
              {termo}
            </pre>
          </div>
          <div className="flex gap-3">
            <Button onClick={exportar} className="flex-1 bg-zinc-700 hover:bg-zinc-600">
              <Download size={15} className="mr-2" />
              Exportar .txt
            </Button>
            <Button
              variant="outline"
              className="flex-1 border-zinc-700 text-zinc-400 hover:text-zinc-200"
              onClick={() => {
                navigator.clipboard.writeText(termo);
              }}
            >
              Copiar texto
            </Button>
            <Button variant="outline" onClick={reiniciar} className="border-zinc-700 text-zinc-400 hover:text-zinc-200">
              <RotateCcw size={15} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
