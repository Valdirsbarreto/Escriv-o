"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAppStore } from "@/store/app";
import { api, getDocsGerados, getDocGerado, deleteDocGerado } from "@/lib/api";
import { deleteInquerito } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FolderOpen, ArrowLeft, Upload, FileText, CheckCircle2, FileType2, Trash2, RefreshCw, Sparkles, Loader2, AlertCircle, Pencil, X, Check, CalendarPlus, Clock, MapPin, ExternalLink, BookOpen, Quote, ChevronDown, ChevronRight, Bot, Eye } from "lucide-react";
import { IntimacaoUploadModal } from "@/components/IntimacaoUploadModal";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// ── Etapas do pipeline ────────────────────────────────────────────────────────

const ETAPAS_LABEL: Record<string, string> = {
  download: "Download",
  extracao: "Extração/OCR",
  chunking: "Chunks",
  embedding: "Embeddings",
  indexacao: "Indexação",
  extracao_entidades: "Entidades",
  resumos_agendados: "Resumos",
  pipeline_completo: "Concluído",
};

function ProgressoPipeline({ inqId, onConcluido }: { inqId: string; onConcluido: () => void }) {
  const [progresso, setProgresso] = useState<any>(null);
  const [concluido, setConcluido] = useState(false);
  const [gerandoSintese, setGerandoSintese] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCount = useRef(0);
  const MAX_POLLS_IDLE = 120; // ~6min sem progresso → exibe botão "Gerar síntese"

  const poll = async () => {
    try {
      const res = await api.get(`/inqueritos/${inqId}/progresso`);
      const data = res.data;
      setProgresso(data);
      if (data.percentual >= 100 && data.sintese_pronta) {
        setConcluido(true);
        if (intervalRef.current) clearInterval(intervalRef.current);
        setTimeout(onConcluido, 2000);
        return;
      }
      // Conta idle apenas quando há docs registrados e todos terminaram
      // (evita parar cedo por causa da race condition orquestrador x documentos)
      if (data.total > 0 && data.processando === 0 && data.pendentes === 0 && !data.sintese_pronta) {
        pollCount.current += 1;
        // Nunca para o polling — apenas exibe o botão manual após MAX_POLLS_IDLE
      } else {
        pollCount.current = 0;
      }
    } catch {
      // silencioso
    }
  };

  const handleGerarSintese = async () => {
    setGerandoSintese(true);
    try {
      await api.post(`/inqueritos/${inqId}/gerar-sintese`);
      pollCount.current = 0;
      if (!intervalRef.current) {
        intervalRef.current = setInterval(poll, 3000);
      }
    } catch {
      alert("Erro ao acionar síntese.");
    } finally {
      setGerandoSintese(false);
    }
  };

  useEffect(() => {
    poll();
    intervalRef.current = setInterval(poll, 3000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [inqId]);

  if (!progresso || progresso.total === 0) return null;
  if (progresso.processando === 0 && progresso.pendentes === 0 && progresso.sintese_pronta && progresso.erros === 0) return null;

  const pct = progresso.percentual;
  const barColor = progresso.erros > 0 ? "bg-red-500" : concluido ? "bg-green-500" : "bg-blue-500";
  const docsOk = progresso.processando === 0 && progresso.pendentes === 0 && progresso.erros === 0;
  const sinteseTrancada = docsOk && !progresso.sintese_pronta && pollCount.current >= MAX_POLLS_IDLE;

  let titulo = "Processando autos...";
  if (concluido) titulo = "Pipeline concluído";
  else if (docsOk && !progresso.sintese_pronta) titulo = "Aguardando Síntese Investigativa...";

  return (
    <div className={`border rounded-xl bg-zinc-900/60 p-5 space-y-4 ${sinteseTrancada ? "border-yellow-500/30" : "border-zinc-800"}`}>
      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {concluido ? (
            <CheckCircle2 size={16} className="text-green-400" />
          ) : docsOk && !progresso.sintese_pronta ? (
            <Sparkles size={16} className="text-yellow-400 animate-pulse" />
          ) : (
            <Loader2 size={16} className="text-blue-400 animate-spin" />
          )}
          <span className="text-sm font-medium text-zinc-200">{titulo}</span>
          {sinteseTrancada && (
            <button
              onClick={handleGerarSintese}
              disabled={gerandoSintese}
              className="ml-2 text-xs text-yellow-400 hover:text-yellow-300 underline underline-offset-2 disabled:opacity-50"
            >
              {gerandoSintese ? "Acionando..." : "Acionar agora"}
            </button>
          )}
        </div>
        <span className="text-xs text-zinc-500">
          {progresso.concluidos}/{progresso.total} docs · {pct}%
        </span>
      </div>

      {/* Barra geral */}
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Etapas globais */}
      <div className="flex gap-1 flex-wrap">
        {Object.entries(ETAPAS_LABEL).map(([key, label]) => {
          const atingida = progresso.docs.some((d: any) =>
            d.ultima_etapa === key && d.ultima_etapa_status === "concluido"
          );
          const atual = progresso.docs.some((d: any) => d.ultima_etapa === key && d.status === "processando");
          return (
            <span
              key={key}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                atingida
                  ? "bg-green-500/15 border-green-500/30 text-green-400"
                  : atual
                  ? "bg-blue-500/15 border-blue-500/30 text-blue-400"
                  : "bg-zinc-800 border-zinc-700 text-zinc-600"
              }`}
            >
              {label}
            </span>
          );
        })}
        {/* Síntese */}
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
            progresso.sintese_pronta
              ? "bg-blue-500/15 border-blue-500/30 text-blue-400"
              : "bg-zinc-800 border-zinc-700 text-zinc-600"
          }`}
        >
          ✨ Síntese
        </span>
      </div>

      {/* Por documento */}
      <div className="space-y-2">
        {progresso.docs.map((doc: any) => (
          <div key={doc.id} className="flex items-center gap-3">
            <div className="shrink-0">
              {doc.status === "concluido" ? (
                <CheckCircle2 size={13} className="text-green-400" />
              ) : doc.status === "erro" ? (
                <AlertCircle size={13} className="text-red-400" />
              ) : (
                <Loader2 size={13} className="text-blue-400 animate-spin" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs text-zinc-400 truncate max-w-[200px]">{doc.nome}</span>
                <span className="text-[10px] text-zinc-600 shrink-0 ml-2">
                  {doc.ultima_etapa ? (ETAPAS_LABEL[doc.ultima_etapa] ?? doc.ultima_etapa) : "aguardando"}
                </span>
              </div>
              <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    doc.status === "erro" ? "bg-red-500" : doc.status === "concluido" ? "bg-green-500" : "bg-blue-500"
                  }`}
                  style={{ width: `${doc.percentual}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function InqueritoDetalhePage() {
  const params = useParams();
  const router = useRouter();
  const inqId = params.id as string;
  const { setInqueritoAtivoId, setCopilotoOpen, docsGeradosVersion } = useAppStore();

  const [inquerito, setInq] = useState<any>(null);
  const [documentos, setDocumentos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [gerandoSintese, setGerandoSintese] = useState(false);
  const [editandoNumero, setEditandoNumero] = useState(false);
  const [novoNumero, setNovoNumero] = useState("");
  const [salvandoNumero, setSalvandoNumero] = useState(false);
  const [intimacoes, setIntimacoes] = useState<any[]>([]);
  const [showIntimacaoModal, setShowIntimacaoModal] = useState(false);
  const [docViewer, setDocViewer] = useState<{ open: boolean; doc: any; conteudo: any | null; loading: boolean }>({ open: false, doc: null, conteudo: null, loading: false });
  const [citacoes, setCitacoes] = useState<{ open: boolean; doc: any | null; fragmentos: any[]; loading: boolean }>({ open: false, doc: null, fragmentos: [], loading: false });
  const [gruposAbertos, setGruposAbertos] = useState<Record<string, boolean>>({});
  const [reclassificando, setReclassificando] = useState(false);
  const [docsGerados, setDocsGerados] = useState<any[]>([]);
  const [docsGeradosLoading, setDocsGeradosLoading] = useState(false);
  const [docGeradoViewer, setDocGeradoViewer] = useState<{ open: boolean; doc: any | null; conteudo: string | null; loading: boolean }>({ open: false, doc: null, conteudo: null, loading: false });
  const [deletingDocGerado, setDeletingDocGerado] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sintesePollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const searchParams = useSearchParams();

  const fetchDocsGerados = async () => {
    setDocsGeradosLoading(true);
    try {
      const res = await getDocsGerados(inqId);
      setDocsGerados(res.data);
    } catch {
      // silencioso
    } finally {
      setDocsGeradosLoading(false);
    }
  };

  const fetchDados = async () => {
    try {
      const [inqRes, docsRes, intRes] = await Promise.all([
        api.get(`/inqueritos/${inqId}`),
        api.get(`/inqueritos/${inqId}/documentos`),
        api.get(`/intimacoes/inquerito/${inqId}`).catch(() => ({ data: [] })),
      ]);
      setInq(inqRes.data);
      setDocumentos(docsRes.data);
      setIntimacoes(intRes.data);
      setInqueritoAtivoId(inqId);
      fetchDocsGerados();

      // Se veio de intimação (?sintese=1), abre a síntese automaticamente
      if (searchParams.get("sintese") === "1") {
        const sintese = docsRes.data.find((d: any) => d.tipo_peca === "sintese_investigativa");
        if (sintese) {
          try {
            const res = await api.get(`/inqueritos/${inqId}/documentos/${sintese.id}/conteudo`);
            setDocViewer({ open: true, doc: sintese, conteudo: res.data, loading: false });
          } catch {
            setDocViewer({ open: true, doc: sintese, conteudo: null, loading: false });
          }
        }
      }
    } catch (e) {
      console.error(e);
      alert("Inquérito não encontrado.");
      router.push("/inqueritos");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (inqId) {
      fetchDados();
      setCopilotoOpen(true);
    }
    return () => {
      setCopilotoOpen(false);
      if (sintesePollingRef.current) clearInterval(sintesePollingRef.current);
    };
  }, [inqId]);

  // Re-busca docs gerados quando o copiloto salva um novo documento
  useEffect(() => {
    if (inqId && docsGeradosVersion > 0) {
      fetchDocsGerados();
    }
  }, [docsGeradosVersion]);

  // Trava scroll do body quando qualquer modal estiver aberto
  useEffect(() => {
    const anyOpen = docGeradoViewer.open || docViewer.open || deleteDialogOpen || showIntimacaoModal || citacoes.open;
    document.body.style.overflow = anyOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [docGeradoViewer.open, docViewer.open, deleteDialogOpen, showIntimacaoModal, citacoes.open]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteInquerito(inqId);
      setDeleteDialogOpen(false);
      router.push("/inqueritos");
    } catch (e) {
      console.error(e);
      setDeleting(false);
      alert("Erro ao excluir inquérito.");
    }
  };

  const handleReprocessar = async () => {
    setReprocessing(true);
    try {
      const res = await api.post(`/inqueritos/${inqId}/reprocessar`);
      await fetchDados();
      alert(res.data.mensagem);
    } catch (e) {
      console.error(e);
      alert("Erro ao reprocessar documentos.");
    } finally {
      setReprocessing(false);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    
    setUploading(true);
    const file = e.target.files[0];
    const formData = new FormData();
    formData.append("file", file);

    try {
      // O Axios precisa saber que não é json
      await api.post(`/inqueritos/${inqId}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      // Atualizar lista
      await fetchDados();
    } catch (error) {
      console.error(error);
      alert("Erro ao fazer upload do documento.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleSalvarNumero = async () => {
    if (!novoNumero.trim()) return;
    setSalvandoNumero(true);
    try {
      await api.patch(`/inqueritos/${inqId}/numero`, { numero: novoNumero.trim() });
      await fetchDados();
      setEditandoNumero(false);
      setNovoNumero("");
    } catch (e) {
      console.error(e);
      alert("Erro ao atualizar número do inquérito.");
    } finally {
      setSalvandoNumero(false);
    }
  };

  const handleAbrirDoc = async (doc: any) => {
    setDocViewer({ open: true, doc, conteudo: null, loading: true });
    try {
      const res = await api.get(`/inqueritos/${inqId}/documentos/${doc.id}/conteudo`);
      setDocViewer(prev => ({ ...prev, conteudo: res.data, loading: false }));
    } catch {
      setDocViewer(prev => ({ ...prev, loading: false }));
    }
  };

  const handleVerCitacoes = async (doc: any, e: React.MouseEvent) => {
    e.stopPropagation();
    setCitacoes({ open: true, doc, fragmentos: [], loading: true });
    try {
      const res = await api.get(`/inqueritos/${inqId}/documentos/${doc.id}/citacoes`);
      setCitacoes(prev => ({ ...prev, fragmentos: res.data.fragmentos || [], loading: false }));
    } catch {
      setCitacoes(prev => ({ ...prev, loading: false }));
    }
  };

  const handleReclassificar = async () => {
    setReclassificando(true);
    try {
      const res = await api.post(`/inqueritos/${inqId}/reclassificar`);
      alert(res.data.mensagem);
      if (res.data.reclassificados > 0) setTimeout(fetchDados, 8000);
    } catch {
      alert("Erro ao solicitar reclassificação.");
    } finally {
      setReclassificando(false);
    }
  };

  const handleGerarSintese = async () => {
    setGerandoSintese(true);
    try {
      await api.post(`/inqueritos/${inqId}/gerar-sintese`);
      // Polling até a síntese aparecer na lista de documentos (máx ~3 min)
      let tentativas = 0;
      sintesePollingRef.current = setInterval(async () => {
        tentativas++;
        try {
          const docsRes = await api.get(`/inqueritos/${inqId}/documentos`);
          const docs = docsRes.data;
          if (docs.some((d: any) => d.tipo_peca === "sintese_investigativa")) {
            setDocumentos(docs);
            setGerandoSintese(false);
            if (sintesePollingRef.current) clearInterval(sintesePollingRef.current);
            return;
          }
        } catch {/* silencioso */}
        if (tentativas >= 36) { // ~3 min
          setGerandoSintese(false);
          if (sintesePollingRef.current) clearInterval(sintesePollingRef.current);
          alert("A geração da síntese está demorando mais que o esperado. Recarregue a página em alguns minutos.");
        }
      }, 5000);
    } catch (e) {
      console.error(e);
      setGerandoSintese(false);
      alert("Erro ao acionar geração da Síntese Investigativa.");
    }
  };

  const handleAbrirDocGerado = async (doc: any) => {
    setDocGeradoViewer({ open: true, doc, conteudo: null, loading: true });
    try {
      const res = await getDocGerado(inqId, doc.id);
      setDocGeradoViewer(prev => ({ ...prev, conteudo: res.data.conteudo, loading: false }));
    } catch {
      setDocGeradoViewer(prev => ({ ...prev, loading: false }));
    }
  };

  const handleDeletarDocGerado = async (docId: string) => {
    if (!confirm("Excluir este documento gerado? Esta ação não pode ser desfeita.")) return;
    setDeletingDocGerado(docId);
    try {
      await deleteDocGerado(inqId, docId);
      setDocsGerados(prev => prev.filter(d => d.id !== docId));
    } catch {
      alert("Erro ao excluir documento.");
    } finally {
      setDeletingDocGerado(null);
    }
  };

  const TIPO_GERADO_LABEL: Record<string, string> = {
    roteiro_oitiva: "Roteiro de Oitiva",
    oficio: "Ofício",
    minuta_cautelar: "Minuta Cautelar",
    relatorio: "Relatório",
    outro: "Outro",
  };

  const TIPO_GERADO_COLOR: Record<string, string> = {
    roteiro_oitiva: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    oficio: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    minuta_cautelar: "bg-orange-500/10 text-orange-400 border-orange-500/20",
    relatorio: "bg-green-500/10 text-green-400 border-green-500/20",
    outro: "bg-zinc-800 text-zinc-400 border-zinc-700",
  };

  if (loading) return <div className="p-8 text-zinc-500 animate-pulse">Carregando autos...</div>;
  if (!inquerito) return null;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 h-full flex flex-col">
      <div className="flex items-start justify-between">
        <div>
          <button 
            onClick={() => router.push("/inqueritos")}
            className="text-zinc-500 hover:text-zinc-300 mb-4 flex items-center gap-1 text-sm font-medium transition-colors"
          >
            <ArrowLeft size={16}/> Voltar para lista
          </button>
          <div className="flex items-center gap-3 flex-wrap">
            {editandoNumero ? (
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  value={novoNumero}
                  onChange={e => setNovoNumero(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") handleSalvarNumero(); if (e.key === "Escape") setEditandoNumero(false); }}
                  placeholder="Ex: 033-07699-2024"
                  className="text-xl font-bold bg-zinc-800 border border-zinc-600 rounded px-3 py-1 text-zinc-100 focus:outline-none focus:border-blue-500 w-56"
                />
                <button onClick={handleSalvarNumero} disabled={salvandoNumero} className="text-green-400 hover:text-green-300 disabled:opacity-50">
                  {salvandoNumero ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />}
                </button>
                <button onClick={() => setEditandoNumero(false)} className="text-zinc-500 hover:text-zinc-300">
                  <X size={18} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
                  {inquerito.numero}
                </h1>
                {inquerito.numero.startsWith("TEMP-") && (
                  <Badge variant="outline" className="text-yellow-400 border-yellow-400/30 bg-yellow-400/10 text-xs">
                    Nº provisório
                  </Badge>
                )}
                {inquerito.numero.startsWith("TEMP-") && (
                  <button
                    onClick={() => { setNovoNumero(""); setEditandoNumero(true); }}
                    className="text-zinc-500 hover:text-zinc-300 transition-colors"
                    title="Corrigir número"
                  >
                    <Pencil size={14} />
                  </button>
                )}
              </div>
            )}
            {inquerito.redistribuido && (
              <Badge variant="outline" className="text-blue-400 border-blue-400/30 bg-blue-400/10">REDISTRIBUÍDO</Badge>
            )}
          </div>
          <p className="text-zinc-400 mt-1">
            {inquerito.redistribuido 
              ? `Origem: ${inquerito.delegacia_origem_nome || inquerito.delegacia} → Atual: ${inquerito.delegacia_atual_nome || inquerito.delegacia_atual_codigo}` 
              : (inquerito.delegacia_origem_nome || inquerito.delegacia)}
          </p>
          <div className="flex items-center gap-3 mt-3">
            <Badge variant="outline" className="bg-zinc-900 border-zinc-700 text-zinc-300">
              {inquerito.estado_atual.toUpperCase()}
            </Badge>
            <span className="text-xs text-zinc-500">ID: {inquerito.id.split("-")[0]}...</span>
          </div>
        </div>
        
        <div className="flex gap-3">
          <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
            <DialogTrigger render={<Button variant="outline" className="border-red-800 text-red-500 hover:bg-red-500/10 hover:text-red-400" />}>
              <Trash2 size={16} className="mr-2"/> Excluir
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-800" showCloseButton={false}>
              <DialogHeader>
                <DialogTitle className="text-zinc-100">Excluir inquérito?</DialogTitle>
                <DialogDescription className="text-zinc-400">
                  Todos os documentos, vetores e dados do inquérito <strong className="text-zinc-200">{inquerito?.numero}/{inquerito?.ano}</strong> serão permanentemente removidos. Esta ação não pode ser desfeita.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDeleteDialogOpen(false)} disabled={deleting} className="bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700">
                  Cancelar
                </Button>
                <Button onClick={handleDelete} disabled={deleting} className="bg-red-700 hover:bg-red-600 text-white">
                  {deleting ? (
                    <><div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin mr-2" />Excluindo...</>
                  ) : "Excluir permanentemente"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Button onClick={() => setShowIntimacaoModal(true)} variant="outline" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
            <CalendarPlus size={16} className="mr-2 text-blue-400" />
            Lançar Intimação
          </Button>
          <Button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="bg-blue-600 hover:bg-blue-700 text-white">
            {uploading ? (
              <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin mr-2" />
            ) : (
              <Upload size={18} className="mr-2"/>
            )}
            {uploading ? "Enviando..." : "Anexar Documento"}
          </Button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            accept=".pdf,.png,.jpg,.jpeg"
          />
        </div>
      </div>

      <ProgressoPipeline inqId={inqId} onConcluido={fetchDados} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Info lateral esquerdo */}
        <div className="space-y-6">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader>
              <CardTitle className="text-lg">Fato Típico</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-zinc-400 whitespace-pre-wrap leading-relaxed">
                {inquerito.descricao || "Sem informações inseridas no formulário inicial."}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Peças Processuais (Lista Docs) */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex justify-between items-end border-b border-zinc-800 pb-2">
            <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
              <FolderOpen className="text-blue-500"/> Autos Físicos Digitalizados
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-zinc-500">{documentos.length} peças anexadas</span>
              {documentos.some(d => d.status_processamento === "concluido" && !d.tipo_peca) && (
                <button
                  onClick={handleReclassificar}
                  disabled={reclassificando}
                  className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1 transition-colors disabled:opacity-50"
                >
                  <FileType2 size={12} className={reclassificando ? "animate-pulse" : ""}/>
                  {reclassificando ? "Classificando..." : "Classificar peças"}
                </button>
              )}
              {documentos.some(d => d.status_processamento === "processando" || d.status_processamento === "erro") && (
                <button
                  onClick={handleReprocessar}
                  disabled={reprocessing}
                  className="text-xs text-yellow-500 hover:text-yellow-400 flex items-center gap-1 transition-colors disabled:opacity-50"
                >
                  <RefreshCw size={12} className={reprocessing ? "animate-spin" : ""}/>
                  {reprocessing ? "Reprocessando..." : "Reprocessar travados"}
                </button>
              )}
              {documentos.every(d => d.status_processamento === "concluido" || d.status_processamento === "sintetico") &&
               !documentos.some(d => d.tipo_peca === "sintese_investigativa") && (
                <button
                  onClick={handleGerarSintese}
                  disabled={gerandoSintese}
                  className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors disabled:opacity-50"
                >
                  <Sparkles size={12} className={gerandoSintese ? "animate-pulse" : ""}/>
                  {gerandoSintese ? "Gerando síntese..." : "Gerar Síntese Investigativa"}
                </button>
              )}
            </div>
          </div>
          
          <ScrollArea className="h-[600px] w-full pr-4">
            <div className="space-y-3">
              {documentos.length === 0 ? (
                <div className="py-12 text-center text-zinc-600 border border-zinc-800 border-dashed rounded-lg bg-zinc-900/40">
                  <FileType2 className="w-12 h-12 mx-auto mb-3 opacity-20" />
                  <p>Inquérito em branco.</p>
                  <p className="text-sm">Faça o upload do inquérito físico em PDF para a IA indexar.</p>
                </div>
              ) : (() => {
                const TIPO_LABEL: Record<string, string> = {
                  boletim_ocorrencia: "Boletim de Ocorrência",
                  auto_prisao_flagrante: "Auto de Prisão em Flagrante",
                  portaria: "Portaria",
                  requerimento_ofendido: "Requerimento do Ofendido",
                  termo_declaracao_vitima: "Declarações da Vítima",
                  termo_oitiva_testemunha: "Oitiva de Testemunha",
                  termo_interrogatorio: "Interrogatório",
                  termo_acareacao: "Acareação",
                  laudo_pericial: "Laudo Pericial",
                  auto_apreensao: "Auto de Apreensão",
                  registro_fotografico: "Registro Fotográfico",
                  oficio: "Ofício / Requisição",
                  quebra_sigilo: "Quebra de Sigilo",
                  mandado_busca_apreensao: "Mandado de Busca e Apreensão",
                  mandado_intimacao: "Mandado de Intimação",
                  folha_antecedentes: "Folha de Antecedentes",
                  extrato_bancario: "Extrato Bancário",
                  relatorio_final: "Relatório Final",
                  termo_indiciamento: "Termo de Indiciamento",
                  despacho: "Despacho",
                  pedido_prorrogacao: "Pedido de Prorrogação",
                  peticao: "Petição",
                  decisao_judicial: "Decisão Judicial",
                  certidao: "Certidão",
                  termo_compromisso: "Termo de Compromisso",
                  relatorio: "Relatório Investigativo",
                  sintese_investigativa: "Síntese Investigativa",
                  outro: "Outro",
                };

                const sintese = documentos.find(d => d.tipo_peca === "sintese_investigativa");
                const demais = documentos.filter(d => d.tipo_peca !== "sintese_investigativa");

                // Agrupar por tipo_peca
                const grupos: Record<string, any[]> = {};
                demais.forEach(doc => {
                  const tipo = doc.tipo_peca || "outro";
                  if (!grupos[tipo]) grupos[tipo] = [];
                  grupos[tipo].push(doc);
                });

                const renderDocCard = (doc: any) => {
                  const isSintetico = doc.status_processamento === "sintetico";
                  return (
                    <div key={doc.id} onClick={() => handleAbrirDoc(doc)}
                      className={`flex justify-between items-center p-3 rounded-lg border transition-colors cursor-pointer ${isSintetico ? "bg-blue-500/5 border-blue-500/20 hover:border-blue-500/40" : "bg-zinc-900/60 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-800/60"}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`p-1.5 rounded border shrink-0 ${isSintetico ? "bg-blue-500/10 text-blue-400 border-blue-500/20" : "bg-zinc-950 text-blue-400 border-zinc-800"}`}>
                          {isSintetico ? <Sparkles size={16}/> : <FileText size={16}/>}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-zinc-200 truncate max-w-xs">{doc.nome_arquivo}</p>
                          <p className="text-xs text-zinc-500 mt-0.5">
                            {isSintetico ? "Gerado pela IA" : `${new Date(doc.created_at).toLocaleDateString("pt-BR")}`}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {doc.status_processamento === "concluido" && (
                          <button
                            onClick={(e) => handleVerCitacoes(doc, e)}
                            className="text-xs text-zinc-400 hover:text-blue-400 flex items-center gap-1 px-2 py-1 rounded border border-zinc-700 hover:border-blue-500/40 transition-colors"
                          >
                            <Quote size={11}/> Citações
                          </button>
                        )}
                        {isSintetico ? (
                          <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-xs">
                            <Sparkles size={10} className="mr-1 inline"/> IA
                          </Badge>
                        ) : doc.status_processamento === "concluido" ? (
                          <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20 text-xs">
                            <CheckCircle2 size={10} className="mr-1 inline"/> Indexado
                          </Badge>
                        ) : doc.status_processamento === "processando" ? (
                          <Badge variant="outline" className="bg-yellow-500/10 text-yellow-500 border-yellow-500/30 text-xs">
                            Lendo IA...
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-zinc-800 text-zinc-400 border-zinc-700 text-xs">
                            {doc.status_processamento}
                          </Badge>
                        )}
                      </div>
                    </div>
                  );
                };

                return (
                  <>
                    {/* Síntese sempre no topo */}
                    {sintese && renderDocCard(sintese)}

                    {/* Grupos por tipo de peça */}
                    {Object.entries(grupos).map(([tipo, docs]) => {
                      const label = TIPO_LABEL[tipo] || tipo;
                      const aberto = gruposAbertos[tipo] !== false; // aberto por padrão
                      return (
                        <div key={tipo} className="border border-zinc-800 rounded-lg overflow-hidden">
                          <button
                            onClick={() => setGruposAbertos(prev => ({ ...prev, [tipo]: !aberto }))}
                            className="w-full flex items-center justify-between px-3 py-2 bg-zinc-900 hover:bg-zinc-800/60 transition-colors text-left"
                          >
                            <div className="flex items-center gap-2">
                              <BookOpen size={14} className="text-zinc-500"/>
                              <span className="text-sm font-medium text-zinc-300">{label}</span>
                              <span className="text-xs text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded-full">{docs.length}</span>
                            </div>
                            {aberto ? <ChevronDown size={14} className="text-zinc-500"/> : <ChevronRight size={14} className="text-zinc-500"/>}
                          </button>
                          {aberto && (
                            <div className="divide-y divide-zinc-800/60 px-2 py-1 space-y-1">
                              {docs.map(renderDocCard)}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </>
                );
              })()}
            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Intimações */}
      {intimacoes.length > 0 && (
        <div className="mt-8">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
            <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
              <CalendarPlus size={18} className="text-blue-400" /> Intimações
            </h2>
            <button
              onClick={() => setShowIntimacaoModal(true)}
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
            >
              + Lançar outra
            </button>
          </div>
          <div className="space-y-3">
            {intimacoes.map((intim: any) => (
              <div key={intim.id} className="flex items-center justify-between border border-zinc-800 rounded-xl px-4 py-3 bg-zinc-900/40">
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-zinc-200">
                    {intim.intimado_nome ?? <span className="text-zinc-500 italic">Nome não extraído</span>}
                    {intim.intimado_qualificacao && (
                      <span className="ml-2 text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-400">
                        {intim.intimado_qualificacao}
                      </span>
                    )}
                  </p>
                  <div className="flex gap-3 text-xs text-zinc-500 flex-wrap">
                    {intim.data_oitiva && (
                      <span className="flex items-center gap-1">
                        <Clock size={11} />
                        {new Date(intim.data_oitiva).toLocaleDateString("pt-BR", {
                          day: "2-digit", month: "2-digit", year: "numeric",
                          hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo",
                        })}
                      </span>
                    )}
                    {intim.local_oitiva && (
                      <span className="flex items-center gap-1">
                        <MapPin size={11} />
                        {intim.local_oitiva}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {intim.google_event_url && (
                    <a
                      href={intim.google_event_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      <ExternalLink size={13} /> Google Agenda
                    </a>
                  )}
                  {!intim.intimado_nome && (
                    <button
                      onClick={async () => {
                        try {
                          await api.post(`/intimacoes/${intim.id}/reprocessar`);
                          setTimeout(fetchDados, 8000);
                        } catch { alert("Erro ao reprocessar."); }
                      }}
                      className="flex items-center gap-1 text-xs text-yellow-500 hover:text-yellow-400 transition-colors"
                      title="Reprocessar extração com Gemini Vision"
                    >
                      <RefreshCw size={12}/> Reextrair
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Documentos Gerados pela IA */}
      <div className="mt-8">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
          <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
            <Bot size={18} className="text-blue-400" /> Documentos Gerados pela IA
          </h2>
          <span className="text-sm text-zinc-500">{docsGerados.length} documento(s)</span>
        </div>
        {docsGeradosLoading ? (
          <div className="flex items-center gap-2 text-zinc-500 py-6">
            <Loader2 size={16} className="animate-spin" /> Carregando documentos gerados...
          </div>
        ) : docsGerados.length === 0 ? (
          <div className="py-10 text-center text-zinc-600 border border-zinc-800 border-dashed rounded-lg bg-zinc-900/40">
            <Bot className="w-10 h-10 mx-auto mb-3 opacity-20" />
            <p>Nenhum documento gerado ainda.</p>
            <p className="text-sm mt-1">Use o Copiloto Investigativo e salve os documentos aqui.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docsGerados.map((doc: any) => (
              <div key={doc.id} className="flex items-center justify-between border border-zinc-800 rounded-xl px-4 py-3 bg-zinc-900/40 hover:border-zinc-700 transition-colors">
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className="p-1.5 rounded border bg-zinc-950 text-blue-400 border-zinc-800 shrink-0">
                    <Bot size={15} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-200 truncate">{doc.titulo}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">
                      {new Date(doc.created_at).toLocaleDateString("pt-BR", {
                        day: "2-digit", month: "2-digit", year: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${TIPO_GERADO_COLOR[doc.tipo] || TIPO_GERADO_COLOR["outro"]}`}>
                    {TIPO_GERADO_LABEL[doc.tipo] || doc.tipo}
                  </span>
                  <button
                    onClick={() => handleAbrirDocGerado(doc)}
                    className="flex items-center gap-1 text-xs text-zinc-400 hover:text-blue-400 px-2 py-1 rounded border border-zinc-700 hover:border-blue-500/40 transition-colors"
                  >
                    <Eye size={11} /> Ver
                  </button>
                  <button
                    onClick={() => handleDeletarDocGerado(doc.id)}
                    disabled={deletingDocGerado === doc.id}
                    className="p-1.5 rounded text-zinc-600 hover:text-red-400 transition-colors disabled:opacity-40"
                    title="Excluir documento"
                  >
                    {deletingDocGerado === doc.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showIntimacaoModal && (
        <IntimacaoUploadModal
          inquerito_id={inqId}
          onClose={() => setShowIntimacaoModal(false)}
          onSuccess={() => {
            setShowIntimacaoModal(false);
            setTimeout(fetchDados, 2000);
          }}
        />
      )}

      {/* Modal de citações / fragmentos Qdrant */}
      {citacoes.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setCitacoes(v => ({ ...v, open: false }))}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl mx-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <Quote size={16} className="text-blue-400 shrink-0"/>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-100 truncate">{citacoes.doc?.nome_arquivo}</p>
                  <p className="text-xs text-zinc-500">Fragmentos indexados no Qdrant</p>
                </div>
              </div>
              <button onClick={() => setCitacoes(v => ({ ...v, open: false }))} className="text-zinc-500 hover:text-zinc-300 p-1 transition-colors ml-4 shrink-0">
                <X size={18}/>
              </button>
            </div>
            <div className="overflow-y-auto flex-1 px-4 py-4 space-y-3">
              {citacoes.loading ? (
                <div className="flex items-center justify-center py-16 text-zinc-500">
                  <Loader2 size={24} className="animate-spin mr-2"/> Carregando fragmentos...
                </div>
              ) : citacoes.fragmentos.length === 0 ? (
                <div className="text-center py-16 text-zinc-500">
                  <Quote size={32} className="mx-auto mb-3 opacity-30"/>
                  <p>Nenhum fragmento indexado para este documento.</p>
                  <p className="text-xs mt-1 text-zinc-600">O documento pode ainda estar em processamento.</p>
                </div>
              ) : (
                citacoes.fragmentos.map((frag: any, i: number) => (
                  <div key={frag.chunk_id || i} className="bg-zinc-800/60 border border-zinc-700/60 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      {frag.pagina_inicial != null && (
                        <span className="text-xs text-zinc-500 bg-zinc-900 border border-zinc-700 px-2 py-0.5 rounded-full">
                          fls. {frag.pagina_inicial}{frag.pagina_final && frag.pagina_final !== frag.pagina_inicial ? `–${frag.pagina_final}` : ""}
                        </span>
                      )}
                      {frag.tipo_peca && (
                        <span className="text-xs text-blue-400/70">{frag.tipo_peca}</span>
                      )}
                    </div>
                    <div className="text-sm text-zinc-300 leading-relaxed selection:bg-blue-500/30">
                      {frag.texto ? (
                        frag.texto.split(/(?:\r?\n\s*){2,}/).map((para: string, j: number) => (
                          <p key={j} className="mb-3 text-justify">
                            {para.replace(/\r?\n/g, ' ')}
                          </p>
                        ))
                      ) : (
                        <span className="text-zinc-600 italic">Texto não disponível</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
            {!citacoes.loading && citacoes.fragmentos.length > 0 && (
              <div className="px-6 py-3 border-t border-zinc-800 text-xs text-zinc-600 shrink-0">
                {citacoes.fragmentos.length} fragmento(s)
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal de visualização de documento gerado */}
      {docGeradoViewer.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setDocGeradoViewer(v => ({ ...v, open: false }))}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl mx-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <Bot size={18} className="text-blue-400 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-100 truncate">{docGeradoViewer.doc?.titulo}</p>
                  <p className="text-xs text-zinc-500">{TIPO_GERADO_LABEL[docGeradoViewer.doc?.tipo] || docGeradoViewer.doc?.tipo}</p>
                </div>
              </div>
              <button onClick={() => setDocGeradoViewer(v => ({ ...v, open: false }))} className="text-zinc-500 hover:text-zinc-300 p-1 transition-colors ml-4 shrink-0">
                <X size={18} />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-4">
              {docGeradoViewer.loading ? (
                <div className="flex items-center justify-center py-16 text-zinc-500">
                  <Loader2 size={24} className="animate-spin mr-2" /> Carregando...
                </div>
              ) : docGeradoViewer.conteudo ? (
                <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {docGeradoViewer.conteudo}
                  </ReactMarkdown>
                </div>
              ) : (
                <div className="text-center py-16 text-zinc-500">
                  <Bot size={32} className="mx-auto mb-3 opacity-30" />
                  <p>Conteúdo não disponível.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal de visualização de documento */}
      {docViewer.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setDocViewer(v => ({ ...v, open: false }))}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl mx-4" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                {docViewer.doc?.status_processamento === "sintetico"
                  ? <Sparkles size={18} className="text-blue-400 shrink-0"/>
                  : <FileText size={18} className="text-blue-400 shrink-0"/>
                }
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-100 truncate">{docViewer.doc?.nome_arquivo}</p>
                  <p className="text-xs text-zinc-500">{docViewer.doc?.tipo_peca || docViewer.doc?.status_processamento}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                {docViewer.conteudo?.download_url && (
                  <a
                    href={docViewer.conteudo.download_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 rounded-lg px-3 py-1.5 transition-colors"
                  >
                    <ExternalLink size={12}/> Abrir PDF
                  </a>
                )}
                <button onClick={() => setDocViewer(v => ({ ...v, open: false }))} className="text-zinc-500 hover:text-zinc-300 p-1 transition-colors">
                  <X size={18}/>
                </button>
              </div>
            </div>
            {/* Conteúdo */}
            <div className="overflow-y-auto flex-1 px-6 py-4">
              {docViewer.loading ? (
                <div className="flex items-center justify-center py-16 text-zinc-500">
                  <Loader2 size={24} className="animate-spin mr-2"/> Carregando...
                </div>
              ) : docViewer.conteudo?.texto_extraido ? (
                <div className="text-sm text-zinc-300 leading-relaxed font-sans selection:bg-blue-500/30">
                  {docViewer.conteudo.texto_extraido.split(/(?:\r?\n\s*){2,}/).map((para: string, i: number) => (
                    <p key={i} className="mb-4 text-justify">
                      {para.replace(/\r?\n/g, ' ')}
                    </p>
                  ))}
                </div>
              ) : (
                <div className="text-center py-16 text-zinc-500">
                  <FileText size={32} className="mx-auto mb-3 opacity-30"/>
                  <p>Texto não disponível para este documento.</p>
                </div>
              )}
            </div>
            {/* Footer */}
            {docViewer.conteudo && (
              <div className="px-6 py-3 border-t border-zinc-800 text-xs text-zinc-600 shrink-0">
                {docViewer.conteudo.total_paginas > 0 && `${docViewer.conteudo.total_paginas} página(s) · `}
                {docViewer.conteudo.texto_extraido?.length?.toLocaleString()} caracteres
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
