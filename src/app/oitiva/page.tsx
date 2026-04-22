"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Mic, MicOff, FileText, Download, RotateCcw, CheckCircle,
  Clock, Loader2, Save, List, Plus, Zap, AlertTriangle,
  HelpCircle, ChevronDown, ChevronUp, Copy, Upload
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  transcreverOitiva, lavrarTermo, lavrarSegmento, sherlockOitiva,
  salvarOitiva, listarOitivas, obterOitiva, deletarOitiva,
  getPessoas, criarPessoa, getInqueritos, criarInqueritoRapido,
  buscarPessoasGlobal,
} from "@/lib/api";
import { useAppStore } from "@/store/app";

type Fase = "idle" | "gravando" | "pronto" | "lista";

interface Qualificacao {
  nome?: string; nascimento?: string; filiacao_materna?: string;
  filiacao_paterna?: string; endereco?: string; profissao?: string;
  estado_civil?: string; cpf?: string; rg?: string;
}

interface SherlockResult {
  consistencia: "consistente" | "inconsistente" | "parcialmente_consistente";
  observacoes: string[];
  inconsistencias: string[];
  perguntas_sugeridas: string[];
}

interface Pessoa { id: string; nome: string; tipo_pessoa: string; }
interface OitivaItem {
  id: string; pessoa_id: string | null; nome_pessoa: string | null;
  audio_url: string | null; duracao_segundos: number | null;
  status: string; created_at: string; preview: string;
}

function formatarDuracao(s: number) {
  const m = Math.floor(s / 60).toString().padStart(2, "0");
  const sec = (s % 60).toString().padStart(2, "0");
  return `${m}:${sec}`;
}

const SEGMENT_MS = 3 * 60 * 1000; // 3 minutos por segmento

export default function OitivaPage() {
  const { inqueritoAtivoId } = useAppStore();

  // ── Fase ──────────────────────────────────────────────────────────────────
  const [fase, setFase] = useState<Fase>("idle");
  const [finalizando, setFinalizando] = useState(false);

  // ── IP local ──────────────────────────────────────────────────────────────
  const [ipLocal, setIpLocal] = useState<{ id: string; numero: string } | null>(null);
  const [buscaIP, setBuscaIP] = useState("");
  const [listaIPs, setListaIPs] = useState<{ id: string; numero: string }[]>([]);
  const [todosIPs, setTodosIPs] = useState<{ id: string; numero: string }[]>([]);
  const [carregandoIPs, setCarregandoIPs] = useState(false);
  const [confirmandoCriarIP, setConfirmandoCriarIP] = useState(false);
  const [criandoIP, setCriandoIP] = useState(false);

  // ID efetivo
  const inqueritoId = ipLocal?.id ?? inqueritoAtivoId;

  // ── Declarante ────────────────────────────────────────────────────────────
  const [papel, setPapel] = useState("testemunha");
  const [pessoaId, setPessoaId] = useState<string | null>(null);
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [novoNome, setNovoNome] = useState("");
  const [criandoPessoa, setCriandoPessoa] = useState(false);
  const [pessoasEncontradas, setPessoasEncontradas] = useState<
    { id: string; nome: string; tipo_pessoa: string; inquerito_numero: string }[]
  >([]);

  // ── Gravação ──────────────────────────────────────────────────────────────
  const [duracao, setDuracao] = useState(0);
  const [segmentoAtual, setSegmentoAtual] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  // ── Documento ─────────────────────────────────────────────────────────────
  const [documentoTexto, setDocumentoTexto] = useState("");
  const [qualificacao, setQualificacao] = useState<Qualificacao | null>(null);
  const [qualExpanded, setQualExpanded] = useState(true);

  // ── Oitiva salva ──────────────────────────────────────────────────────────
  const [oitivaId, setOitivaId] = useState<string | null>(null);
  const [statusOitiva, setStatusOitiva] = useState<"rascunho" | "finalizado">("rascunho");
  const [copiado, setCopiado] = useState(false);

  // ── Sherlock ──────────────────────────────────────────────────────────────
  const [sherlockResult, setSherlockResult] = useState<SherlockResult | null>(null);
  const [sherlockLoading, setSherlockLoading] = useState(false);
  const [sherlockExpanded, setSherlockExpanded] = useState(true);

  // ── Lista ─────────────────────────────────────────────────────────────────
  const [oitivas, setOitivas] = useState<OitivaItem[]>([]);
  const [carregandoLista, setCarregandoLista] = useState(false);

  // ── Erros ─────────────────────────────────────────────────────────────────
  const [erro, setErro] = useState("");

  // ── Refs (estáveis entre renders para callbacks assíncronos) ──────────────
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const isRecordingRef = useRef(false);
  const pendingRef = useRef(0);
  const segmentIdxRef = useRef(0);
  const segmentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const documentoRef = useRef("");
  const transcricaoRef = useRef("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [processandoArquivo, setProcessandoArquivo] = useState(false);
  const sessionRef = useRef<{
    papel: string; pessoaId: string | null; inqueritoId: string | null;
    duracao: number; audioUrl: string | null;
  } | null>(null);

  // ── Carregar IPs (seletor) ─────────────────────────────────────────────────
  useEffect(() => {
    if (inqueritoAtivoId) return;
    setCarregandoIPs(true);
    getInqueritos()
      .then((data: any) => {
        const items = (data.items || data) as any[];
        setTodosIPs(items.map((i: any) => ({ id: i.id, numero: i.numero })));
      })
      .catch(() => {})
      .finally(() => setCarregandoIPs(false));
  }, [inqueritoAtivoId]);

  useEffect(() => {
    if (!buscaIP.trim()) { setListaIPs([]); return; }
    const q = buscaIP.trim().toLowerCase();
    setListaIPs(todosIPs.filter(ip => ip.numero.toLowerCase().includes(q)).slice(0, 8));
  }, [buscaIP, todosIPs]);

  // ── Carregar pessoas ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!inqueritoId) return;
    getPessoas(inqueritoId)
      .then((data: any[]) => setPessoas(data.map(p => ({ id: p.id, nome: p.nome, tipo_pessoa: p.tipo_pessoa }))))
      .catch(() => {});
  }, [inqueritoId]);

  // ── Cross-IP busca pessoa ──────────────────────────────────────────────────
  useEffect(() => {
    if (novoNome.trim().length < 3) { setPessoasEncontradas([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await buscarPessoasGlobal(novoNome.trim());
        setPessoasEncontradas((r as any[]).filter(p => p.inquerito_id !== inqueritoId));
      } catch {}
    }, 500);
    return () => clearTimeout(t);
  }, [novoNome, inqueritoId]);

  // ── Segmented recording ────────────────────────────────────────────────────

  const processarSegmento = useCallback(async (blob: Blob, idx: number) => {
    const session = sessionRef.current;
    if (!session) return;

    pendingRef.current += 1;
    setStatusMsg(`Transcrevendo segmento ${idx + 1}...`);

    try {
      // 1. Transcrever
      const { transcricao, audio_url } = await transcreverOitiva(blob, `seg${idx}.webm`);
      transcricaoRef.current += (transcricaoRef.current ? "\n\n" : "") + transcricao;
      if (idx === 0 && audio_url) {
        session.audioUrl = audio_url;
        setAudioUrl(audio_url);
      }

      // 2. Lavrar segmento → formato "Que,"
      setStatusMsg(`Lavrando segmento ${idx + 1}...`);
      const { texto, qualificacao: qual } = await lavrarSegmento({
        transcricao,
        papel: session.papel,
        segmento_idx: idx,
      });

      // Qualificação só no primeiro segmento
      if (idx === 0 && qual && Object.values(qual).some(v => v)) {
        setQualificacao(qual);
      }

      // Acumular documento
      if (texto.trim()) {
        documentoRef.current += (documentoRef.current ? "\n\n" : "") + texto;
        setDocumentoTexto(documentoRef.current);
      }
    } catch (e: any) {
      setErro(`Erro no segmento ${idx + 1}: ${e?.response?.data?.detail || e.message}`);
    }

    pendingRef.current -= 1;

    if (pendingRef.current === 0) {
      setStatusMsg("");
      if (!isRecordingRef.current) {
        // Última gravação processada — salvar no banco
        await criarOitivaDB(session);
      }
    }
  }, []);

  const criarOitivaDB = async (session: typeof sessionRef.current) => {
    if (!session?.inqueritoId) { setFase("pronto"); return; }
    try {
      const r = await lavrarTermo({
        transcricao: transcricaoRef.current || " ",
        papel: session.papel,
        inquerito_id: session.inqueritoId,
        pessoa_id: session.pessoaId,
        audio_url: session.audioUrl,
        duracao_segundos: session.duracao,
        documento: documentoRef.current || null,
      });
      setOitivaId(r.oitiva_id);
      setStatusOitiva("rascunho");
    } catch (e: any) {
      setErro("Erro ao salvar: " + (e?.response?.data?.detail || e.message));
    }
    setFinalizando(false);
    setFase("pronto");
  };

  const startSegment = useCallback((stream: MediaStream, idx: number) => {
    const chunks: BlobPart[] = [];
    const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
    mr.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    mr.onstop = () => {
      const blob = new Blob(chunks, { type: "audio/webm" });
      processarSegmento(blob, idx);
    };
    mr.start(1000);
    mediaRecorderRef.current = mr;

    // Agendar rotação após SEGMENT_MS
    segmentTimerRef.current = setTimeout(() => {
      if (!isRecordingRef.current || !streamRef.current) return;
      mr.stop(); // dispara onstop do segmento atual
      const nextIdx = idx + 1;
      segmentIdxRef.current = nextIdx;
      setSegmentoAtual(nextIdx);
      startSegment(streamRef.current, nextIdx);
    }, SEGMENT_MS);
  }, [processarSegmento]);

  const iniciarGravacao = useCallback(async () => {
    setErro("");
    documentoRef.current = "";
    transcricaoRef.current = "";
    setDocumentoTexto("");
    setQualificacao(null);
    setOitivaId(null);
    setSherlockResult(null);
    setDuracao(0);
    setSegmentoAtual(0);
    setStatusMsg("");
    setFinalizando(false);
    isRecordingRef.current = true;
    pendingRef.current = 0;
    segmentIdxRef.current = 0;

    // Captura os parâmetros da sessão no momento de início
    sessionRef.current = {
      papel,
      pessoaId,
      inqueritoId,
      duracao: 0,
      audioUrl: null,
    };

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      streamRef.current = stream;
      timerRef.current = setInterval(() => {
        setDuracao(d => {
          if (sessionRef.current) sessionRef.current.duracao = d + 1;
          return d + 1;
        });
      }, 1000);
      setFase("gravando");
      startSegment(stream, 0);
    } catch (e: any) {
      setErro("Microfone: " + e.message);
      isRecordingRef.current = false;
    }
  }, [papel, pessoaId, inqueritoId, startSegment]);

  const pararGravacao = useCallback(() => {
    isRecordingRef.current = false;
    if (segmentTimerRef.current) clearTimeout(segmentTimerRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
    setFinalizando(true);
    mediaRecorderRef.current?.stop(); // dispara onstop do último segmento
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  }, []);

  // ── Sherlock ───────────────────────────────────────────────────────────────

  const consultarSherlock = useCallback(async () => {
    const id = sessionRef.current?.inqueritoId ?? inqueritoId;
    if (!id || !documentoRef.current.trim()) return;
    setSherlockLoading(true);
    setSherlockResult(null);
    try {
      const r = await sherlockOitiva({ inquerito_id: id, documento_atual: documentoRef.current });
      setSherlockResult(r);
      setSherlockExpanded(true);
    } catch (e: any) {
      setErro("Sherlock: " + (e?.response?.data?.detail || e.message));
    }
    setSherlockLoading(false);
  }, [inqueritoId]);

  // ── Salvar / Finalizar ─────────────────────────────────────────────────────

  const salvar = useCallback(async (novoStatus: "rascunho" | "finalizado") => {
    if (!oitivaId) return;
    try {
      await salvarOitiva(oitivaId, {
        termo_com_timestamps: documentoTexto,
        termo_limpo: documentoTexto,
        status: novoStatus,
        pessoa_id: pessoaId,
      });
      setStatusOitiva(novoStatus);
    } catch (e: any) {
      setErro("Erro ao salvar: " + (e?.response?.data?.detail || e.message));
    }
  }, [oitivaId, documentoTexto, pessoaId]);

  const copiar = () => {
    navigator.clipboard.writeText(documentoTexto);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  };

  const exportar = () => {
    const blob = new Blob([documentoTexto], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "declaracoes.txt"; a.click();
    URL.revokeObjectURL(url);
  };

  // ── Pessoa ─────────────────────────────────────────────────────────────────

  const criarNovaPessoa = async () => {
    if (!novoNome.trim() || !inqueritoId) return;
    setCriandoPessoa(true);
    try {
      const nova = await criarPessoa(inqueritoId, {
        nome: novoNome.trim(),
        tipo_pessoa: papel === "investigado" ? "investigado" : papel === "vítima" ? "vitima" : "testemunha",
      });
      setPessoas(prev => [...prev, { id: nova.id, nome: nova.nome, tipo_pessoa: nova.tipo_pessoa }]);
      setPessoaId(nova.id);
      setNovoNome("");
      setPessoasEncontradas([]);
    } catch {}
    setCriandoPessoa(false);
  };

  const vincularQualificacao = async () => {
    if (!qualificacao?.nome || !inqueritoId) return;
    try {
      const nova = await criarPessoa(inqueritoId, {
        nome: qualificacao.nome,
        tipo_pessoa: papel === "investigado" ? "investigado" : papel === "vítima" ? "vitima" : "testemunha",
      });
      setPessoas(prev => [...prev, { id: nova.id, nome: nova.nome, tipo_pessoa: nova.tipo_pessoa }]);
      setPessoaId(nova.id);
    } catch (e: any) {
      setErro("Erro ao vincular: " + e.message);
    }
  };

  // ── Lista de oitivas ───────────────────────────────────────────────────────

  const carregarLista = useCallback(async () => {
    if (!inqueritoId) return;
    setCarregandoLista(true);
    try { setOitivas(await listarOitivas(inqueritoId)); } catch {}
    setCarregandoLista(false);
  }, [inqueritoId]);

  const abrirLista = () => { setFase("lista"); carregarLista(); };

  const carregarOitiva = async (id: string) => {
    try {
      const data = await obterOitiva(id);
      setOitivaId(data.id);
      documentoRef.current = data.termo_com_timestamps || data.termo_limpo || "";
      setDocumentoTexto(documentoRef.current);
      setAudioUrl(data.audio_url);
      setPessoaId(data.pessoa_id);
      setStatusOitiva(data.status);
      setFase("pronto");
    } catch { setErro("Erro ao carregar oitiva."); }
  };

  const excluirOitiva = async (id: string) => {
    try {
      await deletarOitiva(id);
      setOitivas(prev => prev.filter(o => o.id !== id));
    } catch (e: any) { setErro(e?.response?.data?.detail || "Erro ao excluir."); }
  };

  const reiniciar = () => {
    setFase("idle");
    documentoRef.current = "";
    setDocumentoTexto("");
    setOitivaId(null);
    setErro("");
    setDuracao(0);
    setAudioUrl(null);
    setQualificacao(null);
    setSherlockResult(null);
    setStatusMsg("");
  };

  // ── Processar arquivo de áudio direto (modo teste) ────────────────────────
  // Divide transcrição longa em blocos por marcadores de tempo [MM:SS]
  const chunkTranscricao = (texto: string, maxChars = 3000): string[] => {
    const linhas = texto.split("\n").filter(l => l.trim());
    const blocos: string[] = [];
    let atual = "";
    for (const linha of linhas) {
      if (atual.length + linha.length > maxChars && atual) {
        blocos.push(atual.trim());
        atual = linha + "\n";
      } else {
        atual += linha + "\n";
      }
    }
    if (atual.trim()) blocos.push(atual.trim());
    return blocos.length ? blocos : [texto];
  };

  const processarArquivoAudio = async (file: File) => {
    if (!inqueritoId) { setErro("Selecione um inquérito antes de importar o arquivo."); return; }
    setProcessandoArquivo(true);
    setErro("");
    documentoRef.current = "";
    transcricaoRef.current = "";
    setDocumentoTexto("");
    setQualificacao(null);
    setSherlockResult(null);
    setOitivaId(null);

    try {
      // 1. Transcrever arquivo direto (sem microfone)
      setStatusMsg("Transcrevendo arquivo...");
      const { transcricao, audio_url } = await transcreverOitiva(file, file.name);
      transcricaoRef.current = transcricao;

      // 2. Fatiar transcrição e lavrar cada bloco sequencialmente
      const blocos = chunkTranscricao(transcricao, 3000);
      for (let i = 0; i < blocos.length; i++) {
        setStatusMsg(`Lavrando bloco ${i + 1}/${blocos.length}...`);
        const { texto, qualificacao: qual } = await lavrarSegmento({
          transcricao: blocos[i],
          papel,
          segmento_idx: i,
        });
        if (i === 0 && qual && Object.values(qual).some(v => v)) setQualificacao(qual);
        if (texto.trim()) {
          documentoRef.current += (documentoRef.current ? "\n\n" : "") + texto;
          setDocumentoTexto(documentoRef.current);
        }
      }

      // 3. Persistir no banco
      setStatusMsg("Salvando rascunho...");
      const r = await lavrarTermo({
        transcricao,
        papel,
        inquerito_id: inqueritoId,
        pessoa_id: pessoaId,
        audio_url: audio_url || null,
        duracao_segundos: null,
        documento: documentoRef.current || null,
      });
      setOitivaId(r.oitiva_id);
      setStatusOitiva("rascunho");
    } catch (e: any) {
      setErro("Erro ao processar arquivo: " + (e?.response?.data?.detail || e.message));
    }

    setStatusMsg("");
    setProcessandoArquivo(false);
    setFase("pronto");
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const corSherlock = sherlockResult
    ? sherlockResult.consistencia === "consistente" ? "text-green-400 border-green-700/40 bg-green-900/10"
    : sherlockResult.consistencia === "inconsistente" ? "text-red-400 border-red-700/40 bg-red-900/10"
    : "text-amber-400 border-amber-700/40 bg-amber-900/10"
    : "";

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="border-b border-zinc-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
            <Mic size={20} className="text-red-400" />
            Modo Oitiva
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Grave, transcreva e lavre declarações no padrão técnico-policial.
          </p>
        </div>
        <button onClick={abrirLista} className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 rounded-md px-3 py-1.5">
          <List size={14} /> Oitivas salvas
        </button>
      </div>

      {/* Erro */}
      {erro && (
        <div className="rounded-lg bg-red-900/20 border border-red-700/40 p-3 text-sm text-red-300 flex items-start gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>{erro}</span>
          <button onClick={() => setErro("")} className="ml-auto text-red-400 hover:text-red-200">✕</button>
        </div>
      )}

      {/* ── LISTA ── */}
      {fase === "lista" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-zinc-300">Oitivas registradas neste inquérito</span>
            <button onClick={reiniciar} className="text-xs text-zinc-500 hover:text-zinc-300">Nova oitiva</button>
          </div>
          {carregandoLista ? (
            <div className="flex items-center gap-2 text-zinc-500 text-sm py-4"><Loader2 size={16} className="animate-spin" /> Carregando...</div>
          ) : oitivas.length === 0 ? (
            <p className="text-sm text-zinc-600 py-4">Nenhuma oitiva registrada.</p>
          ) : oitivas.map(o => (
            <div key={o.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-zinc-200">{o.nome_pessoa || "Declarante não identificado"}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${o.status === "finalizado" ? "bg-green-900/40 text-green-400" : "bg-amber-900/40 text-amber-400"}`}>
                    {o.status}
                  </span>
                </div>
                <p className="text-xs text-zinc-500 truncate">{o.preview || "(sem conteúdo)"}</p>
                <p className="text-xs text-zinc-700 mt-1">{new Date(o.created_at).toLocaleString("pt-BR")}</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => carregarOitiva(o.id)} className="text-xs text-blue-400 hover:text-blue-300 border border-blue-800 rounded px-2 py-1">Abrir</button>
                {o.status !== "finalizado" && (
                  <button onClick={() => excluirOitiva(o.id)} className="text-xs text-red-400 hover:text-red-300 border border-red-800/50 rounded px-2 py-1">✕</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── IDLE ── */}
      {fase === "idle" && (
        <div className="space-y-4">
          {/* Seletor de IP */}
          <div className="rounded-lg border border-zinc-700 bg-zinc-900/70 p-4 space-y-2">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold flex items-center gap-2">
              <FileText size={12} /> Inquérito policial
            </p>
            {inqueritoId ? (
              <div className="flex items-center justify-between">
                <span className="text-sm text-zinc-200 font-mono">
                  {ipLocal?.numero ?? "(IP ativo do workspace)"}
                </span>
                {ipLocal && (
                  <button onClick={() => { setIpLocal(null); setBuscaIP(""); setPessoas([]); setPessoaId(null); }}
                    className="text-xs text-zinc-500 hover:text-zinc-300">trocar</button>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="relative">
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                    placeholder={carregandoIPs ? "Carregando IPs..." : "Digite o nº do IP (ex: 911-00001/2024)"}
                    value={buscaIP}
                    disabled={carregandoIPs}
                    onChange={e => { setBuscaIP(e.target.value); setConfirmandoCriarIP(false); }}
                  />
                  {carregandoIPs && <Loader2 size={12} className="absolute right-3 top-2.5 animate-spin text-zinc-500" />}
                </div>
                {listaIPs.length > 0 && (
                  <div className="border border-zinc-700 rounded-md overflow-hidden">
                    {listaIPs.map(ip => (
                      <button key={ip.id}
                        onClick={() => { setIpLocal(ip); setBuscaIP(""); setListaIPs([]); setConfirmandoCriarIP(false); }}
                        className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 font-mono border-b border-zinc-800 last:border-0">
                        {ip.numero}
                      </button>
                    ))}
                  </div>
                )}
                {buscaIP.length >= 5 && listaIPs.length === 0 && !carregandoIPs && (
                  confirmandoCriarIP ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-amber-400 flex-1">Cadastrar IP <span className="font-mono font-semibold">{buscaIP}</span>?</span>
                      <button onClick={async () => {
                        setCriandoIP(true); setErro("");
                        try {
                          const novo = await criarInqueritoRapido(buscaIP.trim());
                          setIpLocal({ id: novo.id, numero: novo.numero });
                          setBuscaIP(""); setConfirmandoCriarIP(false);
                        } catch (e: any) { setErro(e?.response?.data?.detail || "Formato inválido. Use: NNN-NNNNN/AAAA"); }
                        setCriandoIP(false);
                      }} disabled={criandoIP}
                        className="text-xs bg-amber-700 hover:bg-amber-600 text-white rounded px-3 py-1 disabled:opacity-50 flex items-center gap-1">
                        {criandoIP ? <Loader2 size={12} className="animate-spin" /> : "Confirmar"}
                      </button>
                      <button onClick={() => setConfirmandoCriarIP(false)} className="text-xs text-zinc-500 hover:text-zinc-300">Cancelar</button>
                    </div>
                  ) : (
                    <button onClick={() => setConfirmandoCriarIP(true)} className="text-xs text-zinc-500 hover:text-zinc-300 underline">
                      Não encontrado — cadastrar como novo IP?
                    </button>
                  )
                )}
              </div>
            )}
          </div>

          {/* Dados do declarante */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Dados do declarante</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Papel nos autos</label>
                <select className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  value={papel} onChange={e => setPapel(e.target.value)}>
                  <option value="testemunha">Testemunha</option>
                  <option value="vítima">Vítima</option>
                  <option value="investigado">Investigado</option>
                  <option value="informante">Informante</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-zinc-400 mb-1 block">Pessoa nos autos</label>
                <select className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  value={pessoaId || ""} onChange={e => setPessoaId(e.target.value || null)}>
                  <option value="">— não vincular —</option>
                  {pessoas.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </div>
            </div>
            <div className="flex gap-2 items-center">
              <input className="flex-1 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Ou cadastre nova pessoa..."
                value={novoNome} onChange={e => setNovoNome(e.target.value)}
                onKeyDown={e => e.key === "Enter" && criarNovaPessoa()} />
              <button onClick={criarNovaPessoa} disabled={!novoNome.trim() || criandoPessoa || !inqueritoId}
                className="flex items-center gap-1 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-zinc-200 rounded-md px-3 py-1.5">
                {criandoPessoa ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Criar
              </button>
            </div>
            {pessoasEncontradas.length > 0 && (
              <div className="rounded-md bg-amber-900/20 border border-amber-700/40 p-2 text-xs text-amber-300 space-y-1">
                <p className="font-semibold">Pessoa encontrada em outro(s) IP(s):</p>
                {pessoasEncontradas.map(p => (
                  <div key={p.id}><span className="font-mono">{p.inquerito_numero}</span> — {p.nome} <span className="text-amber-500">({p.tipo_pessoa || "sem tipo"})</span></div>
                ))}
              </div>
            )}
          </div>

          {/* Botão gravar */}
          <div className="flex flex-col items-center gap-4 py-6">
            <button onClick={iniciarGravacao}
              className="w-24 h-24 rounded-full bg-red-600 hover:bg-red-500 active:scale-95 transition-all flex items-center justify-center shadow-lg shadow-red-900/40">
              <Mic size={36} className="text-white" />
            </button>
            <p className="text-sm text-zinc-500">Clique para iniciar a gravação</p>

            {/* Importar arquivo (modo teste) */}
            <div className="flex flex-col items-center gap-1 pt-2 border-t border-zinc-800 w-full">
              <input ref={fileInputRef} type="file" accept="audio/*,.mp3,.wav,.ogg,.webm,.m4a"
                className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) processarArquivoAudio(f); e.target.value = ""; }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={processandoArquivo || !inqueritoId}
                className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 disabled:opacity-40 transition-colors py-1"
              >
                {processandoArquivo
                  ? <><Loader2 size={12} className="animate-spin" /> {statusMsg || "Processando..."}</>
                  : <><Upload size={12} /> Importar arquivo de áudio (teste)</>
                }
              </button>
              {!inqueritoId && <p className="text-[10px] text-zinc-600">Selecione um IP para habilitar</p>}
            </div>
          </div>
        </div>
      )}

      {/* ── GRAVANDO ── */}
      {fase === "gravando" && (
        <div className="space-y-4">
          {/* Status bar */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-red-400 animate-ping" />
                <span className="text-sm text-zinc-300 font-medium">
                  {finalizando ? "Finalizando..." : `Gravando — Segmento ${segmentoAtual + 1}`}
                </span>
              </div>
              <div className="flex items-center gap-1 text-zinc-400">
                <Clock size={13} />
                <span className="font-mono text-sm">{formatarDuracao(duracao)}</span>
              </div>
            </div>
            {statusMsg && (
              <span className="text-xs text-zinc-500 flex items-center gap-1">
                <Loader2 size={11} className="animate-spin" /> {statusMsg}
              </span>
            )}
          </div>

          {/* Documento crescendo */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Declarações</p>
              {documentoTexto && (
                <button onClick={consultarSherlock} disabled={sherlockLoading}
                  className="flex items-center gap-1.5 text-xs text-purple-400 hover:text-purple-300 border border-purple-800/50 rounded px-2 py-1 disabled:opacity-50">
                  {sherlockLoading ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
                  Sherlock
                </button>
              )}
            </div>
            <textarea
              className="w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-4 text-sm text-zinc-200 leading-relaxed font-serif min-h-[300px] resize-none focus:outline-none focus:ring-1 focus:ring-zinc-600"
              value={documentoTexto}
              readOnly
              placeholder={statusMsg ? statusMsg : "As declarações aparecerão aqui à medida que cada segmento for transcrito..."}
            />
            {documentoTexto && (
              <p className="text-xs text-zinc-600 text-right">{documentoTexto.length} chars</p>
            )}
          </div>

          {/* Sherlock resultado */}
          {sherlockResult && (
            <div className={`rounded-lg border p-4 space-y-3 ${corSherlock}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap size={14} />
                  <span className="text-sm font-semibold">Sherlock — {sherlockResult.consistencia.replace("_", " ")}</span>
                </div>
                <button onClick={() => setSherlockExpanded(v => !v)}>
                  {sherlockExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
              </div>
              {sherlockExpanded && (
                <>
                  {sherlockResult.inconsistencias.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold opacity-80">Inconsistências</p>
                      {sherlockResult.inconsistencias.map((inc, i) => (
                        <p key={i} className="text-xs opacity-90">• {inc}</p>
                      ))}
                    </div>
                  )}
                  {sherlockResult.observacoes.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold opacity-80">Observações</p>
                      {sherlockResult.observacoes.map((obs, i) => (
                        <p key={i} className="text-xs opacity-90">• {obs}</p>
                      ))}
                    </div>
                  )}
                  {sherlockResult.perguntas_sugeridas.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold opacity-80 flex items-center gap-1">
                        <HelpCircle size={11} /> Perguntas sugeridas
                      </p>
                      {sherlockResult.perguntas_sugeridas.map((p, i) => (
                        <p key={i} className="text-xs opacity-90 pl-3 border-l border-current/30">{p}</p>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Botão parar */}
          <div className="flex flex-col items-center gap-3 pt-2">
            <button onClick={pararGravacao} disabled={finalizando}
              className="w-20 h-20 rounded-full bg-zinc-700 hover:bg-zinc-600 active:scale-95 transition-all flex items-center justify-center disabled:opacity-50">
              <MicOff size={30} className="text-white" />
            </button>
            <p className="text-sm text-zinc-500">
              {finalizando ? "Aguarde — processando..." : "Clique para parar a gravação"}
            </p>
          </div>
        </div>
      )}

      {/* ── PRONTO ── */}
      {fase === "pronto" && (
        <div className="space-y-4">
          {/* Barra de ações */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-2 mr-auto">
              <CheckCircle size={15} className={statusOitiva === "finalizado" ? "text-green-400" : "text-amber-400"} />
              <span className="text-sm font-semibold text-zinc-300">{statusOitiva === "finalizado" ? "Finalizado" : "Rascunho"}</span>
            </div>
            <button onClick={copiar}
              className={`text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1 ${copiado ? "bg-green-700 border-green-600 text-white" : "border-zinc-700 text-zinc-400 hover:text-zinc-200"}`}>
              <Copy size={11} /> {copiado ? "Copiado!" : "Copiar"}
            </button>
            <button onClick={exportar} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-zinc-200 flex items-center gap-1">
              <Download size={11} /> .txt
            </button>
            {oitivaId && (
              <button onClick={() => salvar("rascunho")} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-zinc-200 flex items-center gap-1">
                <Save size={11} /> Salvar
              </button>
            )}
            {oitivaId && statusOitiva !== "finalizado" && (
              <button onClick={() => salvar("finalizado")} className="text-xs px-3 py-1.5 rounded-md bg-green-700 hover:bg-green-600 text-white flex items-center gap-1">
                <CheckCircle size={11} /> Finalizar
              </button>
            )}
            <button onClick={consultarSherlock} disabled={sherlockLoading}
              className="text-xs px-3 py-1.5 rounded-md border border-purple-800/50 text-purple-400 hover:text-purple-300 flex items-center gap-1 disabled:opacity-50">
              {sherlockLoading ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
              Sherlock
            </button>
          </div>

          {/* Qualificação detectada */}
          {qualificacao && Object.values(qualificacao).some(v => v) && (
            <div className="rounded-lg border border-blue-700/40 bg-blue-900/10 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-blue-400 uppercase tracking-wider">Qualificação detectada</p>
                <button onClick={() => setQualExpanded(v => !v)}>
                  {qualExpanded ? <ChevronUp size={14} className="text-blue-400" /> : <ChevronDown size={14} className="text-blue-400" />}
                </button>
              </div>
              {qualExpanded && (
                <>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    {qualificacao.nome && <div><span className="text-zinc-500">Nome: </span><span className="text-zinc-200">{qualificacao.nome}</span></div>}
                    {qualificacao.nascimento && <div><span className="text-zinc-500">Nascimento: </span><span className="text-zinc-200">{qualificacao.nascimento}</span></div>}
                    {qualificacao.filiacao_materna && <div><span className="text-zinc-500">Mãe: </span><span className="text-zinc-200">{qualificacao.filiacao_materna}</span></div>}
                    {qualificacao.filiacao_paterna && <div><span className="text-zinc-500">Pai: </span><span className="text-zinc-200">{qualificacao.filiacao_paterna}</span></div>}
                    {qualificacao.endereco && <div className="col-span-2"><span className="text-zinc-500">Endereço: </span><span className="text-zinc-200">{qualificacao.endereco}</span></div>}
                    {qualificacao.profissao && <div><span className="text-zinc-500">Profissão: </span><span className="text-zinc-200">{qualificacao.profissao}</span></div>}
                    {qualificacao.estado_civil && <div><span className="text-zinc-500">Estado civil: </span><span className="text-zinc-200">{qualificacao.estado_civil}</span></div>}
                    {qualificacao.cpf && <div><span className="text-zinc-500">CPF: </span><span className="text-zinc-200">{qualificacao.cpf}</span></div>}
                    {qualificacao.rg && <div><span className="text-zinc-500">RG: </span><span className="text-zinc-200">{qualificacao.rg}</span></div>}
                  </div>
                  {!pessoaId && (
                    <button onClick={vincularQualificacao}
                      className="text-xs bg-blue-700 hover:bg-blue-600 text-white rounded px-3 py-1.5 flex items-center gap-1">
                      <Plus size={11} /> Vincular como pessoa nos autos
                    </button>
                  )}
                </>
              )}
            </div>
          )}

          {/* Documento editável */}
          <div className="space-y-1">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Declarações</p>
            <textarea
              className="w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-4 text-sm text-zinc-200 leading-relaxed font-serif min-h-[400px] resize-y focus:outline-none focus:ring-1 focus:ring-zinc-500"
              value={documentoTexto}
              onChange={e => {
                documentoRef.current = e.target.value;
                setDocumentoTexto(e.target.value);
              }}
            />
            <p className="text-xs text-zinc-600 text-right">{documentoTexto.length} chars</p>
          </div>

          {/* Sherlock resultado */}
          {sherlockResult && (
            <div className={`rounded-lg border p-4 space-y-3 ${corSherlock}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap size={14} />
                  <span className="text-sm font-semibold">Sherlock — {sherlockResult.consistencia.replace("_", " ")}</span>
                </div>
                <button onClick={() => setSherlockExpanded(v => !v)}>
                  {sherlockExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
              </div>
              {sherlockExpanded && (
                <>
                  {sherlockResult.inconsistencias.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold opacity-80">Inconsistências</p>
                      {sherlockResult.inconsistencias.map((inc, i) => (
                        <p key={i} className="text-xs opacity-90">• {inc}</p>
                      ))}
                    </div>
                  )}
                  {sherlockResult.observacoes.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold opacity-80">Observações</p>
                      {sherlockResult.observacoes.map((obs, i) => (
                        <p key={i} className="text-xs opacity-90">• {obs}</p>
                      ))}
                    </div>
                  )}
                  {sherlockResult.perguntas_sugeridas.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold opacity-80 flex items-center gap-1">
                        <HelpCircle size={11} /> Perguntas sugeridas
                      </p>
                      {sherlockResult.perguntas_sugeridas.map((p, i) => (
                        <p key={i} className="text-xs opacity-90 pl-3 border-l border-current/30">{p}</p>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          <div className="pt-2">
            <Button variant="outline" onClick={reiniciar} className="border-zinc-700 text-zinc-400 hover:text-zinc-200 text-xs">
              <RotateCcw size={13} className="mr-1.5" /> Nova oitiva
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
