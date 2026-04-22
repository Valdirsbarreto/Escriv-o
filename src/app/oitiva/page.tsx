"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Mic, MicOff, FileText, Download, RotateCcw, CheckCircle,
  Clock, Loader2, RefreshCw, Save, ChevronDown, ChevronUp,
  Trash2, Play, Pause, List, Plus
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  transcreverOitiva, lavrarTermo, relavrarBloco, salvarOitiva,
  listarOitivas, obterOitiva, deletarOitiva, getPessoas,
  criarPessoa, getInqueritos, criarInqueritoRapido, buscarPessoasGlobal,
} from "@/lib/api";
import { useAppStore } from "@/store/app";

type Fase = "idle" | "gravando" | "processando" | "transcricao" | "lavrando" | "pronto" | "lista";

interface Bloco {
  id: string;
  textoOriginal: string;   // com [MM:SS]
  textoLimpo: string;      // sem timestamp
  timestamp: string | null; // "MM:SS" extraído
  editando: boolean;
  relavrando: boolean;
}

interface OitivaItem {
  id: string;
  pessoa_id: string | null;
  nome_pessoa: string | null;
  audio_url: string | null;
  duracao_segundos: number | null;
  status: string;
  created_at: string;
  preview: string;
}

interface Pessoa {
  id: string;
  nome: string;
  tipo_pessoa: string;
}

function parseBlocos(texto: string): Bloco[] {
  // Divide por linha e agrupa itens P&R (cada item pode ter 1-2 linhas)
  const linhas = texto.split("\n").filter(l => l.trim());
  return linhas.map((linha, i) => {
    const tsMatch = linha.match(/^\[(\d{1,2}:\d{2})\]\s*/);
    const timestamp = tsMatch ? tsMatch[1] : null;
    const textoLimpo = linha.replace(/^\[\d{1,2}:\d{2}\]\s*/, "").trim();
    return {
      id: `bloco-${i}`,
      textoOriginal: linha,
      textoLimpo,
      timestamp,
      editando: false,
      relavrando: false,
    };
  });
}

function formatarDuracao(s: number) {
  const m = Math.floor(s / 60).toString().padStart(2, "0");
  const sec = (s % 60).toString().padStart(2, "0");
  return `${m}:${sec}`;
}

export default function OitivaPage() {
  const [fase, setFase] = useState<Fase>("idle");
  const [duracao, setDuracao] = useState(0);
  const [transcricao, setTranscricao] = useState("");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioObjectUrl, setAudioObjectUrl] = useState<string | null>(null);
  const [blocos, setBlocos] = useState<Bloco[]>([]);
  const [oitivaId, setOitivaId] = useState<string | null>(null);
  const [statusOitiva, setStatusOitiva] = useState<"rascunho" | "finalizado">("rascunho");
  const [erro, setErro] = useState("");
  const [copiado, setCopiado] = useState(false);

  const [papel, setPapel] = useState("testemunha");
  const [pessoaId, setPessoaId] = useState<string | null>(null);
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [novoNome, setNovoNome] = useState("");
  const [criandoPessoa, setCriandoPessoa] = useState(false);

  // Seletor de IP local (usado quando não há inquéritoAtivoId)
  const [ipLocal, setIpLocal] = useState<{ id: string; numero: string } | null>(null);
  const [buscaIP, setBuscaIP] = useState("");
  const [listaIPs, setListaIPs] = useState<{ id: string; numero: string }[]>([]);
  const [todosIPs, setTodosIPs] = useState<{ id: string; numero: string }[]>([]);
  const [carregandoIPs, setCarregandoIPs] = useState(false);
  const [confirmandoCriarIP, setConfirmandoCriarIP] = useState(false);
  const [criandoIP, setCriandoIP] = useState(false);

  // Cross-IP busca pessoa
  const [pessoasEncontradas, setPessoasEncontradas] = useState<
    { id: string; nome: string; tipo_pessoa: string; inquerito_numero: string }[]
  >([]);

  const [oitivas, setOitivas] = useState<OitivaItem[]>([]);
  const [carregandoLista, setCarregandoLista] = useState(false);

  const [audioPlaying, setAudioPlaying] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const { inqueritoAtivoId } = useAppStore();

  // ID efetivo: preferência para seleção local na página, fallback para store global
  const inqueritoId = ipLocal?.id ?? inqueritoAtivoId;

  // Carrega todos os IPs uma vez (para o seletor de busca)
  useEffect(() => {
    if (inqueritoAtivoId) return; // já tem IP ativo, não precisa do seletor
    setCarregandoIPs(true);
    getInqueritos()
      .then((data: any) => {
        const items = (data.items || data) as any[];
        setTodosIPs(items.map((i: any) => ({ id: i.id, numero: i.numero })));
      })
      .catch(() => {})
      .finally(() => setCarregandoIPs(false));
  }, [inqueritoAtivoId]);

  // Filtra IPs conforme digitação
  useEffect(() => {
    if (!buscaIP.trim()) { setListaIPs([]); return; }
    const q = buscaIP.trim().toLowerCase();
    setListaIPs(todosIPs.filter(ip => ip.numero.toLowerCase().includes(q)).slice(0, 8));
  }, [buscaIP, todosIPs]);

  // Carrega pessoas ao montar ou ao selecionar IP
  useEffect(() => {
    if (!inqueritoId) return;
    getPessoas(inqueritoId)
      .then((data: any[]) => setPessoas(data.map(p => ({ id: p.id, nome: p.nome, tipo_pessoa: p.tipo_pessoa }))))
      .catch(() => {});
  }, [inqueritoId]);

  // Cross-IP busca de pessoa (debounced 500ms)
  useEffect(() => {
    if (novoNome.trim().length < 3) { setPessoasEncontradas([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await buscarPessoasGlobal(novoNome.trim());
        // Só mostrar se for em IPs diferentes do ativo
        setPessoasEncontradas((r as any[]).filter(p => p.inquerito_id !== inqueritoId));
      } catch {}
    }, 500);
    return () => clearTimeout(t);
  }, [novoNome, inqueritoId]);

  const iniciarGravacao = useCallback(async () => {
    setErro("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.start(1000);
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
    mr.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      // URL local para o player
      const objUrl = URL.createObjectURL(blob);
      setAudioObjectUrl(objUrl);
      setFase("processando");
      try {
        const r = await transcreverOitiva(blob, "oitiva.webm");
        setTranscricao(r.transcricao);
        setAudioUrl(r.audio_url);
        setFase("transcricao");
      } catch (e: any) {
        setErro("Erro na transcrição: " + (e?.response?.data?.detail || e.message));
        setFase("idle");
      }
    };
    mr.stop();
    mr.stream.getTracks().forEach(t => t.stop());
    mediaRecorderRef.current = null;
  }, []);

  const lavrar = useCallback(async () => {
    if (!inqueritoId) {
      setErro("Selecione um inquérito antes de lavrar.");
      return;
    }
    setFase("lavrando");
    setErro("");
    try {
      const r = await lavrarTermo({
        transcricao,
        papel,
        inquerito_id: inqueritoId,
        pessoa_id: pessoaId,
        audio_url: audioUrl,
        duracao_segundos: duracao || null,
      });
      setOitivaId(r.oitiva_id);
      setBlocos(parseBlocos(r.termo_com_timestamps));
      setStatusOitiva("rascunho");
      setFase("pronto");
    } catch (e: any) {
      setErro("Erro ao lavrar termo: " + (e?.response?.data?.detail || e.message));
      setFase("transcricao");
    }
  }, [transcricao, papel, inqueritoId, pessoaId, audioUrl, duracao]);

  const handleRelavrarBloco = useCallback(async (idx: number) => {
    const bloco = blocos[idx];
    setBlocos(prev => prev.map((b, i) => i === idx ? { ...b, relavrando: true } : b));
    try {
      const r = await relavrarBloco({ trecho: bloco.textoOriginal, papel });
      const novoBloco = parseBlocos(r.bloco_com_timestamps)[0];
      setBlocos(prev => prev.map((b, i) => i === idx
        ? { ...b, ...novoBloco, id: b.id, relavrando: false, editando: false }
        : b
      ));
    } catch {
      setBlocos(prev => prev.map((b, i) => i === idx ? { ...b, relavrando: false } : b));
    }
  }, [blocos, papel]);

  const handleEditBloco = (idx: number, novoTexto: string) => {
    setBlocos(prev => prev.map((b, i) => {
      if (i !== idx) return b;
      const tsMatch = novoTexto.match(/^\[(\d{1,2}:\d{2})\]\s*/);
      return {
        ...b,
        textoOriginal: novoTexto,
        textoLimpo: novoTexto.replace(/^\[\d{1,2}:\d{2}\]\s*/, "").trim(),
        timestamp: tsMatch ? tsMatch[1] : b.timestamp,
      };
    }));
  };

  const toggleEditBloco = (idx: number) => {
    setBlocos(prev => prev.map((b, i) => i === idx ? { ...b, editando: !b.editando } : b));
  };

  const salvar = useCallback(async (novoStatus: "rascunho" | "finalizado") => {
    if (!oitivaId) return;
    const termoComTs = blocos.map(b => b.textoOriginal).join("\n");
    const termoLimpo = blocos.map(b => b.textoLimpo).join("\n");
    try {
      await salvarOitiva(oitivaId, { termo_com_timestamps: termoComTs, termo_limpo: termoLimpo, status: novoStatus, pessoa_id: pessoaId });
      setStatusOitiva(novoStatus);
    } catch (e: any) {
      setErro("Erro ao salvar: " + (e?.response?.data?.detail || e.message));
    }
  }, [oitivaId, blocos, pessoaId]);

  const copiarTextoLimpo = () => {
    const texto = blocos.map(b => b.textoLimpo).join("\n");
    navigator.clipboard.writeText(texto);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  };

  const exportar = () => {
    const texto = blocos.map(b => b.textoLimpo).join("\n");
    const blob = new Blob([texto], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "declaracoes.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const saltarParaTimestamp = (ts: string) => {
    if (!audioRef.current) return;
    const [min, sec] = ts.split(":").map(Number);
    audioRef.current.currentTime = min * 60 + sec;
    audioRef.current.play();
    setAudioPlaying(true);
  };

  const carregarLista = useCallback(async () => {
    if (!inqueritoId) return;
    setCarregandoLista(true);
    try {
      const data = await listarOitivas(inqueritoId);
      setOitivas(data);
    } catch {}
    setCarregandoLista(false);
  }, [inqueritoId]);

  const abrirLista = () => { setFase("lista"); carregarLista(); };

  const carregarOitiva = async (id: string) => {
    try {
      const data = await obterOitiva(id);
      setOitivaId(data.id);
      setBlocos(parseBlocos(data.termo_com_timestamps || ""));
      setAudioUrl(data.audio_url);
      setPessoaId(data.pessoa_id);
      setStatusOitiva(data.status);
      setFase("pronto");
    } catch (e: any) {
      setErro("Erro ao carregar oitiva.");
    }
  };

  const excluirOitiva = async (id: string) => {
    try {
      await deletarOitiva(id);
      setOitivas(prev => prev.filter(o => o.id !== id));
    } catch (e: any) {
      setErro(e?.response?.data?.detail || "Erro ao excluir.");
    }
  };

  const criarNovaPessoa = async () => {
    if (!novoNome.trim() || !inqueritoId) return;
    setCriandoPessoa(true);
    try {
      const nova = await criarPessoa(inqueritoId, { nome: novoNome.trim(), tipo_pessoa: papel === "investigado" ? "investigado" : papel === "vítima" ? "vitima" : "testemunha" });
      setPessoas(prev => [...prev, { id: nova.id, nome: nova.nome, tipo_pessoa: nova.tipo_pessoa }]);
      setPessoaId(nova.id);
      setNovoNome("");
      setPessoasEncontradas([]);
    } catch {}
    setCriandoPessoa(false);
  };

  const reiniciar = () => {
    setFase("idle");
    setTranscricao("");
    setBlocos([]);
    setOitivaId(null);
    setErro("");
    setDuracao(0);
    setAudioUrl(null);
    if (audioObjectUrl) { URL.revokeObjectURL(audioObjectUrl); setAudioObjectUrl(null); }
  };

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
          <List size={14} />
          Oitivas salvas
        </button>
      </div>

      {/* Erro */}
      {erro && (
        <div className="rounded-lg bg-red-900/20 border border-red-700/40 p-3 text-sm text-red-300">
          {erro}
        </div>
      )}

      {/* LISTA DE OITIVAS SALVAS */}
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
                  <button onClick={() => excluirOitiva(o.id)} className="text-xs text-red-400 hover:text-red-300">
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* IDLE / GRAVANDO */}
      {(fase === "idle" || fase === "gravando") && (
        <div className="space-y-4">
          {fase === "idle" && (
            <>
              {/* Seletor de Inquérito */}
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
                      <button
                        onClick={() => { setIpLocal(null); setBuscaIP(""); setPessoas([]); setPessoaId(null); }}
                        className="text-xs text-zinc-500 hover:text-zinc-300"
                      >
                        trocar
                      </button>
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
                      {carregandoIPs && (
                        <Loader2 size={12} className="absolute right-3 top-2.5 animate-spin text-zinc-500" />
                      )}
                    </div>
                    {listaIPs.length > 0 && (
                      <div className="border border-zinc-700 rounded-md overflow-hidden">
                        {listaIPs.map(ip => (
                          <button
                            key={ip.id}
                            onClick={() => { setIpLocal(ip); setBuscaIP(""); setListaIPs([]); setConfirmandoCriarIP(false); }}
                            className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 font-mono border-b border-zinc-800 last:border-0"
                          >
                            {ip.numero}
                          </button>
                        ))}
                      </div>
                    )}
                    {buscaIP.length >= 5 && listaIPs.length === 0 && !carregandoIPs && (
                      confirmandoCriarIP ? (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-amber-400 flex-1">
                            Cadastrar IP <span className="font-mono font-semibold">{buscaIP}</span>?
                          </span>
                          <button
                            onClick={async () => {
                              setCriandoIP(true);
                              setErro("");
                              try {
                                const novo = await criarInqueritoRapido(buscaIP.trim());
                                setIpLocal({ id: novo.id, numero: novo.numero });
                                setBuscaIP(""); setConfirmandoCriarIP(false);
                              } catch (e: any) {
                                setErro(e?.response?.data?.detail || "Formato inválido. Use: NNN-NNNNN/AAAA");
                              }
                              setCriandoIP(false);
                            }}
                            disabled={criandoIP}
                            className="text-xs bg-amber-700 hover:bg-amber-600 text-white rounded px-3 py-1 disabled:opacity-50 flex items-center gap-1"
                          >
                            {criandoIP ? <Loader2 size={12} className="animate-spin" /> : "Confirmar"}
                          </button>
                          <button onClick={() => setConfirmandoCriarIP(false)} className="text-xs text-zinc-500 hover:text-zinc-300">
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setConfirmandoCriarIP(true)}
                          className="text-xs text-zinc-500 hover:text-zinc-300 underline"
                        >
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
                    <label className="text-xs text-zinc-400 mb-1 block">Pessoa nos autos</label>
                    <select
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      value={pessoaId || ""}
                      onChange={e => setPessoaId(e.target.value || null)}
                    >
                      <option value="">— não vincular —</option>
                      {pessoas.map(p => (
                        <option key={p.id} value={p.id}>{p.nome}</option>
                      ))}
                    </select>
                  </div>
                </div>
                {/* Cadastro rápido de pessoa */}
                <div className="flex gap-2 items-center">
                  <input
                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="Ou cadastre nova pessoa..."
                    value={novoNome}
                    onChange={e => setNovoNome(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && criarNovaPessoa()}
                  />
                  <button
                    onClick={criarNovaPessoa}
                    disabled={!novoNome.trim() || criandoPessoa || !inqueritoId}
                    className="flex items-center gap-1 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-zinc-200 rounded-md px-3 py-1.5"
                  >
                    {criandoPessoa ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                    Criar
                  </button>
                </div>
                {/* Banner cross-IP */}
                {pessoasEncontradas.length > 0 && (
                  <div className="rounded-md bg-amber-900/20 border border-amber-700/40 p-2 text-xs text-amber-300 space-y-1">
                    <p className="font-semibold">Pessoa encontrada em outro(s) IP(s):</p>
                    {pessoasEncontradas.map(p => (
                      <div key={p.id}>
                        <span className="font-mono">{p.inquerito_numero}</span>
                        {" — "}{p.nome} <span className="text-amber-500">({p.tipo_pessoa || "sem tipo"})</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

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

      {/* PROCESSANDO */}
      {fase === "processando" && (
        <div className="flex flex-col items-center gap-3 py-12">
          <Loader2 size={32} className="text-blue-400 animate-spin" />
          <p className="text-zinc-400">Transcrevendo com Gemini...</p>
          <p className="text-xs text-zinc-600">Aguarde — gravações longas podem levar alguns segundos.</p>
        </div>
      )}

      {/* TRANSCRIÇÃO */}
      {fase === "transcricao" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-zinc-300">Transcrição bruta</span>
              <span className="text-xs text-zinc-600">{transcricao.length} chars</span>
            </div>
            <textarea
              className="w-full bg-zinc-800/50 border border-zinc-700 rounded-md p-3 text-sm text-zinc-300 leading-relaxed focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
              rows={10}
              value={transcricao}
              onChange={e => setTranscricao(e.target.value)}
            />
            <p className="text-xs text-zinc-600 mt-1">Corrija a transcrição se necessário antes de lavrar.</p>
          </div>
          <div className="flex gap-3">
            <Button onClick={lavrar} className="flex-1 bg-blue-600 hover:bg-blue-500">
              <FileText size={15} className="mr-2" />
              Lavrar Declarações
            </Button>
            <Button variant="outline" onClick={reiniciar} className="border-zinc-700 text-zinc-400 hover:text-zinc-200">
              <RotateCcw size={15} />
            </Button>
          </div>
        </div>
      )}

      {/* LAVRANDO */}
      {fase === "lavrando" && (
        <div className="flex flex-col items-center gap-3 py-12">
          <Loader2 size={32} className="text-blue-400 animate-spin" />
          <p className="text-zinc-400">Lavrando declarações no padrão formal...</p>
        </div>
      )}

      {/* PRONTO — blocos editáveis */}
      {fase === "pronto" && (
        <div className="space-y-4">
          {/* Status + ações */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle size={16} className={statusOitiva === "finalizado" ? "text-green-400" : "text-amber-400"} />
              <span className="text-sm font-semibold text-zinc-300">
                {statusOitiva === "finalizado" ? "Finalizado" : "Rascunho"}
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={copiarTextoLimpo}
                className={`text-xs px-3 py-1.5 rounded-md border transition-colors ${copiado ? "bg-green-700 border-green-600 text-white" : "border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"}`}
              >
                {copiado ? "Copiado!" : "Copiar para colar"}
              </button>
              <button onClick={exportar} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-zinc-200 flex items-center gap-1">
                <Download size={12} /> .txt
              </button>
              <button onClick={() => salvar("rascunho")} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-zinc-200 flex items-center gap-1">
                <Save size={12} /> Salvar
              </button>
              {statusOitiva !== "finalizado" && (
                <button onClick={() => salvar("finalizado")} className="text-xs px-3 py-1.5 rounded-md bg-green-700 hover:bg-green-600 text-white flex items-center gap-1">
                  <CheckCircle size={12} /> Finalizar
                </button>
              )}
            </div>
          </div>

          {/* Player de áudio */}
          {audioObjectUrl && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
              <p className="text-xs text-zinc-500 mb-2">Gravação — clique em [MM:SS] para saltar no áudio</p>
              <audio
                ref={audioRef}
                src={audioObjectUrl}
                controls
                className="w-full h-8"
                onPlay={() => setAudioPlaying(true)}
                onPause={() => setAudioPlaying(false)}
              />
            </div>
          )}

          {/* Blocos P&R */}
          <div className="space-y-2">
            {blocos.map((bloco, idx) => (
              <div key={bloco.id} className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
                <div className="flex items-start gap-2">
                  {/* Timestamp clicável */}
                  {bloco.timestamp && (
                    <button
                      onClick={() => saltarParaTimestamp(bloco.timestamp!)}
                      className="shrink-0 text-[10px] font-mono text-blue-400 hover:text-blue-300 bg-blue-900/20 border border-blue-800/50 rounded px-1.5 py-0.5 mt-0.5"
                      title="Saltar para este trecho no áudio"
                    >
                      [{bloco.timestamp}]
                    </button>
                  )}
                  <div className="flex-1 min-w-0">
                    {bloco.editando ? (
                      <textarea
                        className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-sm text-zinc-200 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
                        rows={3}
                        value={bloco.textoOriginal}
                        onChange={e => handleEditBloco(idx, e.target.value)}
                      />
                    ) : (
                      <p className="text-sm text-zinc-300 leading-relaxed">{bloco.textoLimpo}</p>
                    )}
                  </div>
                  {/* Ações do bloco */}
                  <div className="shrink-0 flex gap-1">
                    <button
                      onClick={() => toggleEditBloco(idx)}
                      className="text-xs text-zinc-500 hover:text-zinc-300 px-1.5 py-0.5 rounded border border-zinc-700"
                      title="Editar"
                    >
                      {bloco.editando ? "OK" : "✏"}
                    </button>
                    <button
                      onClick={() => handleRelavrarBloco(idx)}
                      disabled={bloco.relavrando}
                      className="text-xs text-zinc-500 hover:text-zinc-300 px-1.5 py-0.5 rounded border border-zinc-700 disabled:opacity-40"
                      title="Re-lavrar este bloco"
                    >
                      {bloco.relavrando ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="flex gap-3 pt-2">
            <Button variant="outline" onClick={reiniciar} className="border-zinc-700 text-zinc-400 hover:text-zinc-200 text-xs">
              <RotateCcw size={13} className="mr-1.5" /> Nova oitiva
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
