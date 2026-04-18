"use client";

import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { useAppStore } from "@/store/app";

const PDFViewer = dynamic(() => import("@/components/PDFViewer"), { ssr: false });
import { api, getDocsGerados, getDocGerado, deleteDocGerado, updateDocGerado, getPecasExtraidas, getPecaExtraida, reextrairPecas, osintConsultasInquerito, sherlockAnalise as sherlockApi, uploadPorUrl } from "@/lib/api";
import { OneDrivePicker } from "@/components/OneDrivePicker";
import { PainelInvestigacao } from "@/components/osint/PainelInvestigacao";
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
import { FolderOpen, ArrowLeft, Upload, FileText, CheckCircle2, FileType2, Trash2, RefreshCw, Sparkles, Loader2, AlertCircle, Pencil, X, Check, CalendarPlus, Clock, MapPin, ExternalLink, BookOpen, Quote, ChevronDown, ChevronRight, Bot, Eye, UserSearch, Network, Search, Microscope, ShieldAlert, ListChecks, Scale, Swords, Copy, ClipboardCheck } from "lucide-react";
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
              className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
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
          className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
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
                <span className="text-xs text-zinc-600 shrink-0 ml-2">
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

// ── Badge de Processos em Background ─────────────────────────────────────────

function ProcessosBgBadge({ inqId }: { inqId: string }) {
  const [bg, setBg] = useState<any>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await api.get(`/inqueritos/${inqId}/progresso`);
        const pb = res.data?.processos_bg;
        if (pb) setBg(pb);
        if (pb?.status === "concluido" || pb?.status === "erro") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch { /* silencioso */ }
    };
    poll();
    intervalRef.current = setInterval(poll, 15000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [inqId]);

  if (!bg) return null;

  const etapas = [
    { key: "indexacao", label: "Indexação" },
    { key: "sintese", label: "Síntese" },
    { key: "pecas", label: "Peças" },
    { key: "analise", label: "Análise" },
  ];

  const cor = bg.status === "concluido"
    ? "border-green-500/30 bg-green-500/10 text-green-400"
    : bg.status === "erro"
    ? "border-red-500/30 bg-red-500/10 text-red-400"
    : "border-blue-500/30 bg-blue-500/10 text-blue-400";

  const icone = bg.status === "concluido"
    ? <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
    : bg.status === "erro"
    ? <span className="w-2 h-2 rounded-full bg-red-400 inline-block" />
    : <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse inline-block" />;

  return (
    <div className={`group relative inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold cursor-default ${cor}`}>
      {icone}
      <span>
        {bg.status === "concluido" ? "Processado" : bg.status === "erro" ? "Erro" : "Processando"}
      </span>
      {/* Tooltip com detalhe por etapa */}
      <div className="absolute left-0 top-full mt-2 z-50 hidden group-hover:block bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl min-w-[180px]">
        <p className="text-xs text-zinc-500 uppercase tracking-widest mb-2">Processos internos</p>
        {etapas.map(({ key, label }) => {
          const s = bg[key];
          return (
            <div key={key} className="flex items-center justify-between py-0.5">
              <span className="text-xs text-zinc-400">{label}</span>
              <span className={`text-xs font-bold uppercase ${
                s === "concluido" ? "text-green-400" : s === "pendente" ? "text-zinc-600" : "text-blue-400"
              }`}>
                {s === "concluido" ? "✓" : s === "pendente" ? "—" : "⟳"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function InqueritoDetalhePage() {
  const params = useParams();
  const router = useRouter();
  const inqId = params.id as string;
  const { setInqueritoAtivoId, setCopilotoOpen, docsGeradosVersion, setSidebarCollapsed, pdfViewer, setPdfViewer, closePdfViewer, pecaParaAbrir, setPecaParaAbrir } = useAppStore();
  const [activeTab, setActiveTab] = useState<"workspace" | "autos" | "investigacao" | "blockchain">("workspace");

  const [inquerito, setInq] = useState<any>(null);
  const [documentos, setDocumentos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [gerandoSintese, setGerandoSintese] = useState(false);
  const [gerandoRelatorio, setGerandoRelatorio] = useState(false);
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
  const [editDocGerado, setEditDocGerado] = useState<{ open: boolean; id: string; titulo: string; tipo: string; conteudo: string; saving: boolean } | null>(null);
  const [deletingDoc, setDeletingDoc] = useState<string | null>(null);
  const [pecasExtraidas, setPecasExtraidas] = useState<any[]>([]);
  const [pecasLoading, setPecasLoading] = useState(false);
  const [pecaViewer, setPecaViewer] = useState<{ open: boolean; peca: any | null; loading: boolean }>({ open: false, peca: null, loading: false });
  const [reextrahindo, setReextrahindo] = useState<string | null>(null);
  const [extractProgress, setExtractProgress] = useState<number>(0);
  const [editandoNumero, setEditandoNumero] = useState(false);
  const [novoNumero, setNovoNumero] = useState("");
  const [salvandoNumero, setSalvandoNumero] = useState(false);
  const [catalogando, setCatalogando] = useState(false);
  const [consultasOsint, setConsultasOsint] = useState<any[]>([]);
  const [osintAbertos, setOsintAbertos] = useState<Record<string, boolean>>({});
  const [copiadoDocId, setCopiadoDocId] = useState<string | null>(null);
  const [sherlockAnalise, setSherlockAnalise] = useState<any>(null);
  const [sherlockLoading, setSherlockLoading] = useState(false);
  const [sherlockErro, setSherlockErro] = useState<string | null>(null);
  const [sherlockSecaoAberta, setSherlockSecaoAberta] = useState<string | null>("resumo");
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

  const fetchPecasExtraidas = async () => {
    setPecasLoading(true);
    try {
      const res = await getPecasExtraidas(inqId);
      setPecasExtraidas(res.data);
    } catch {
      // silencioso
    } finally {
      setPecasLoading(false);
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
      fetchPecasExtraidas();
      osintConsultasInquerito(inqId).then(r => setConsultasOsint(r.consultas || [])).catch(() => {});

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
      setSidebarCollapsed(true);
    }
    return () => {
      setCopilotoOpen(false);
      setSidebarCollapsed(false);
      if (sintesePollingRef.current) clearInterval(sintesePollingRef.current);
    };
  }, [inqId]);

  // Re-busca docs gerados quando o copiloto salva um novo documento
  useEffect(() => {
    if (inqId && docsGeradosVersion > 0) {
      fetchDocsGerados();
    }
  }, [docsGeradosVersion]);

  // Polling automático enquanto houver docs em geração (em_processamento=true)
  useEffect(() => {
    const temProcessando = docsGerados.some((d: any) => d.em_processamento === true);
    if (!temProcessando) return;
    const timer = setTimeout(() => { if (inqId) fetchDocsGerados(); }, 8000);
    return () => clearTimeout(timer);
  }, [docsGerados, inqId]);

  // Trava scroll do body quando qualquer modal estiver aberto
  useEffect(() => {
    const anyOpen = docGeradoViewer.open || docViewer.open || deleteDialogOpen || showIntimacaoModal || citacoes.open || pecaViewer.open;
    document.body.style.overflow = anyOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [docGeradoViewer.open, docViewer.open, deleteDialogOpen, showIntimacaoModal, citacoes.open, pecaViewer.open]);

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

  const handleOneDriveFile = async (file: { nome: string; downloadUrl: string }) => {
    setUploading(true);
    try {
      await uploadPorUrl(inqId, file.downloadUrl, file.nome);
      await fetchDados();
    } catch (e: any) {
      const detalhe = e?.response?.data?.detail || e?.message || "Erro desconhecido";
      alert(`Erro ao importar do OneDrive: ${detalhe}`);
    } finally {
      setUploading(false);
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

  const handleCatalogarPecas = async () => {
    setCatalogando(true);
    try {
      await api.post(`/inqueritos/${inqId}/reextrair-pecas-lote`);
      alert("Catalogação iniciada. As peças aparecerão em alguns minutos.");
      await fetchPecasExtraidas();
    } catch {
      alert("Erro ao iniciar catalogação.");
    } finally {
      setCatalogando(false);
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

  const handleGerarRelatorioInicial = async (forcar = false) => {
    setGerandoRelatorio(true);
    // Captura o timestamp do início para detectar doc novo (quando forcar=true)
    const iniciadoEm = Date.now();
    try {
      await api.post(`/inqueritos/${inqId}/gerar-relatorio-inicial?forcar=${forcar}`);
      // Polling: aguarda até 10 min pelo doc (novo ou existente se forcar=false)
      let tentativas = 0;
      const relatorioInterval = setInterval(async () => {
        tentativas++;
        try {
          const res = await api.get(`/inqueritos/${inqId}/docs-gerados`);
          const docs = res.data || [];
          const docRelatorio = docs.find((d: any) => d.tipo === "relatorio_inicial");
          // Se forcar=true, espera um doc criado APÓS o início (not the old one)
          const pronto = docRelatorio && (
            !forcar || new Date(docRelatorio.created_at).getTime() > iniciadoEm - 5000
          );
          if (pronto) {
            setGerandoRelatorio(false);
            clearInterval(relatorioInterval);
            setDocsGerados(docs);
            return;
          }
        } catch {/* silencioso */}
        if (tentativas >= 120) { // ~10 min
          setGerandoRelatorio(false);
          clearInterval(relatorioInterval);
          alert("A Síntese Inicial está demorando mais que o esperado. Recarregue a página em alguns minutos.");
        }
      }, 5000);
    } catch (e) {
      console.error(e);
      setGerandoRelatorio(false);
      alert("Erro ao acionar geração da Síntese Inicial.");
    }
  };

  const handleSherlock = async (forcar = false) => {
    setSherlockLoading(true);
    setSherlockErro(null);
    try {
      const res = await sherlockApi(inqId, forcar);
      setSherlockAnalise(res.analise);
      setSherlockSecaoAberta("resumo");
    } catch (e: any) {
      const detalhe = e?.response?.data?.detail || e?.message || "Erro desconhecido";
      setSherlockErro(detalhe);
    } finally {
      setSherlockLoading(false);
    }
  };

  const handleAbrirDocGerado = async (doc: any) => {
    if (doc.em_processamento) return;  // doc ainda sendo gerado
    setDocGeradoViewer({ open: true, doc, conteudo: null, loading: true });
    try {
      const res = await getDocGerado(inqId, doc.id);
      setDocGeradoViewer(prev => ({ ...prev, conteudo: res.data.conteudo, loading: false }));
    } catch {
      setDocGeradoViewer(prev => ({ ...prev, loading: false }));
    }
  };

  const handleDeletarDoc = async (docId: string, nomeArquivo: string) => {
    if (!confirm(`Excluir "${nomeArquivo}"?\n\nOs chunks, vetores e peças extraídas deste documento serão removidos permanentemente.`)) return;
    setDeletingDoc(docId);
    try {
      await api.delete(`/inqueritos/${inqId}/documentos/${docId}`);
      setDocumentos(prev => prev.filter((d: any) => d.id !== docId));
    } catch {
      alert("Erro ao excluir documento.");
    } finally {
      setDeletingDoc(null);
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

  const handleAbrirEditDocGerado = async (doc: any) => {
    // Carrega conteúdo completo se necessário e abre o editor
    let conteudo = doc.conteudo ?? null;
    if (!conteudo && inqId) {
      try {
        const r = await getDocGerado(inqId, doc.id);
        conteudo = r.data?.conteudo ?? "";
      } catch { conteudo = ""; }
    }
    setEditDocGerado({ open: true, id: doc.id, titulo: doc.titulo, tipo: doc.tipo, conteudo: conteudo ?? "", saving: false });
  };

  const handleSalvarEditDocGerado = async () => {
    if (!editDocGerado || !inqId) return;
    setEditDocGerado(prev => prev ? { ...prev, saving: true } : null);
    try {
      await updateDocGerado(inqId, editDocGerado.id, { titulo: editDocGerado.titulo, tipo: editDocGerado.tipo, conteudo: editDocGerado.conteudo });
      setDocsGerados(prev => prev.map(d => d.id === editDocGerado.id ? { ...d, titulo: editDocGerado.titulo, tipo: editDocGerado.tipo } : d));
      setEditDocGerado(null);
    } catch {
      alert("Erro ao salvar edição.");
      setEditDocGerado(prev => prev ? { ...prev, saving: false } : null);
    }
  };

  const markdownParaTextoLimpo = (md: string): string => {
    return md
      // Títulos: remove os # e deixa o texto em maiúsculo seguido de linha em branco
      .replace(/^#{1,6}\s+(.+)$/gm, (_, t) => `\n${t.toUpperCase()}\n`)
      // Negrito e itálico: remove marcadores, mantém texto
      .replace(/\*{1,3}(.+?)\*{1,3}/g, "$1")
      .replace(/_{1,2}(.+?)_{1,2}/g, "$1")
      // Linhas horizontais → linha em branco
      .replace(/^[-*_]{3,}$/gm, "")
      // Listas não ordenadas → bullet simples com recuo
      .replace(/^\s*[-*+]\s+(.+)$/gm, "  • $1")
      // Listas ordenadas → mantém numeração
      .replace(/^\s*(\d+)\.\s+(.+)$/gm, "  $1. $2")
      // Links: mantém só o texto
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      // Código inline: remove backticks
      .replace(/`([^`]+)`/g, "$1")
      // Blocos de código: remove delimitadores
      .replace(/```[\s\S]*?```/g, "")
      // Colapsa mais de 2 linhas em branco seguidas em 2
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  };

  const handleCopiarTextoLimpo = async (doc: any) => {
    let conteudo = doc.conteudo ?? "";
    if (!conteudo && inqId) {
      try {
        const r = await getDocGerado(inqId, doc.id);
        conteudo = r.data?.conteudo ?? "";
      } catch {}
    }
    if (!conteudo) { alert("Conteúdo não disponível."); return; }

    const isHtml = /<[a-zA-Z][^>]*>/.test(conteudo);
    let textoFinal: string;
    if (isHtml) {
      // Strip HTML tags para obter texto plano
      const tmp = document.createElement("div");
      tmp.innerHTML = conteudo;
      textoFinal = tmp.innerText || tmp.textContent || "";
    } else {
      textoFinal = markdownParaTextoLimpo(conteudo);
    }

    try {
      await navigator.clipboard.writeText(textoFinal);
      // Feedback visual breve — troca o ícone por 2s
      setCopiadoDocId(doc.id);
      setTimeout(() => setCopiadoDocId(null), 2000);
    } catch {
      // Fallback: abre janela com o texto selecionado para copiar manualmente
      const win = window.open("", "_blank");
      if (!win) { alert("Permita popups para copiar o texto."); return; }
      win.document.write(`<html><body><pre style="font-family:Arial;font-size:12pt;white-space:pre-wrap">${textoFinal.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}</pre></body></html>`);
      win.document.close();
    }
  };

  const handleExportarDocGeradoPDF = async (doc: any) => {
    let conteudo = doc.conteudo ?? "";
    if (!conteudo && inqId) {
      try {
        const r = await getDocGerado(inqId, doc.id);
        conteudo = r.data?.conteudo ?? "";
      } catch {}
    }
    if (!conteudo) { alert("Conteúdo não disponível para exportação."); return; }

    const tipoLabel = TIPO_GERADO_LABEL[doc.tipo] || doc.tipo || "—";
    const numIp = inquerito?.numero ?? "";
    const data = new Date(doc.created_at).toLocaleDateString("pt-BR");

    // Detecta se é HTML ou markdown/texto plano
    const isHtml = /<[a-zA-Z][^>]*>/.test(conteudo);
    const corpo = isHtml
      ? conteudo
      : `<pre style="white-space:pre-wrap;word-wrap:break-word;font-family:inherit;font-size:11.5pt">${conteudo.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}</pre>`;

    const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <title>${doc.titulo || tipoLabel}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 12pt; line-height: 1.7; margin: 2.5cm; color: #111; }
    h1 { font-size: 13pt; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid #999; padding-bottom: 6px; margin-bottom: 4px; }
    .meta { font-size: 9.5pt; color: #555; margin-bottom: 1.2cm; }
    @page { margin: 2cm; }
    @media print { body { margin: 0; } }
  </style>
</head>
<body>
  <h1>${doc.titulo || tipoLabel}</h1>
  <div class="meta">${[numIp, tipoLabel, data].filter(Boolean).join("&nbsp;&nbsp;|&nbsp;&nbsp;")}</div>
  ${corpo}
</body>
</html>`;

    const win = window.open("", "_blank");
    if (!win) { alert("Permita popups neste site para exportar o PDF."); return; }
    win.document.write(html);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 400);
  };

  const handleAbrirPeca = async (peca: any) => {
    // Se já temos conteudo_texto no objeto, usa direto; senão busca
    if (peca.conteudo_texto) {
      setPecaViewer({ open: true, peca, loading: false });
      return;
    }
    setPecaViewer({ open: true, peca, loading: true });
    try {
      const res = await getPecaExtraida(inqId, peca.id);
      setPecaViewer({ open: true, peca: res.data, loading: false });
    } catch {
      setPecaViewer(prev => ({ ...prev, loading: false }));
    }
  };

  // Exporta o texto da peça como PDF via impressão do browser
  const handleExportarPecaPDF = async (peca: any) => {
    let texto = peca.conteudo_texto ?? "";
    if (!texto && inqId) {
      try {
        const r = await getPecaExtraida(inqId, peca.id);
        texto = r.data?.conteudo_texto ?? "";
      } catch {}
    }
    if (!texto) { alert("Conteúdo não disponível para exportação."); return; }

    const tipoLabel = TIPO_PECA_LABEL[peca.tipo] || peca.tipo || "—";
    const folhas = peca.pagina_inicial != null
      ? `Fls. ${peca.pagina_inicial}${peca.pagina_final && peca.pagina_final !== peca.pagina_inicial ? `–${peca.pagina_final}` : ""}`
      : "";
    const numIp = inquerito?.numero ?? "";

    const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <title>${peca.titulo || "Peça"}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 12pt; line-height: 1.7; margin: 2.5cm; color: #111; }
    h1 { font-size: 13pt; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid #999; padding-bottom: 6px; margin-bottom: 4px; }
    .meta { font-size: 9.5pt; color: #555; margin-bottom: 1.2cm; }
    pre { white-space: pre-wrap; word-wrap: break-word; font-family: inherit; font-size: 11.5pt; }
    @page { margin: 2cm; }
    @media print { body { margin: 0; } }
  </style>
</head>
<body>
  <h1>${peca.titulo || "Documento"}</h1>
  <div class="meta">${[numIp, tipoLabel, folhas].filter(Boolean).join("&nbsp;&nbsp;|&nbsp;&nbsp;")}</div>
  <pre>${texto.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</pre>
</body>
</html>`;

    const win = window.open("", "_blank");
    if (!win) { alert("Permita popups neste site para exportar o PDF."); return; }
    win.document.write(html);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 400);
  };

  // Abre o PDF original na página da peça (mantido para uso interno do Copiloto)
  const handleAbrirPecaNoPDF = async (peca: any) => {
    if (!peca.documento_id) { handleAbrirPeca(peca); return; }
    setPdfViewer({ url: null, page: peca.pagina_inicial ?? 1, titulo: peca.titulo, docId: peca.documento_id });
    try {
      const res = await api.get(`/inqueritos/${inqId}/documentos/${peca.documento_id}/conteudo`);
      const { download_url } = res.data;
      if (!download_url) { closePdfViewer(); handleAbrirPeca(peca); return; }
      setPdfViewer({ url: download_url, page: peca.pagina_inicial ?? 1, titulo: peca.titulo, docId: peca.documento_id });
    } catch {
      closePdfViewer();
      handleAbrirPeca(peca);
    }
  };

  // Reage ao comando <ABRIR_PECA> emitido pelo copiloto
  useEffect(() => {
    if (!pecaParaAbrir) return;
    const peca = pecasExtraidas.find((p: any) => p.id === pecaParaAbrir.pecaId);
    if (peca) {
      handleAbrirPecaNoPDF(peca);
    } else {
      getPecaExtraida(inqId, pecaParaAbrir.pecaId)
        .then(res => handleAbrirPecaNoPDF(res.data))
        .catch(() => {});
    }
    setPecaParaAbrir(null);
  }, [pecaParaAbrir]);

  const handleReextrairPecas = async (docId: string) => {
    setReextrahindo(docId);
    setExtractProgress(5);
    try {
      await reextrairPecas(inqId, docId);

      // Barra de progresso visual simulada até 90%
      const progInterval = setInterval(() => {
        setExtractProgress(prev => {
          if (prev >= 90) return 90;
          return prev + Math.floor(Math.random() * 3) + 1;
        });
      }, 3000);

      // Polling a cada 5s por até 3 minutos (36 × 5s = 180s > timeout Gemini de 120s)
      let chamadas = 0;
      const poll = setInterval(async () => {
        chamadas++;
        try {
          const res = await api.get(`/inqueritos/${inqId}/pecas-extraidas`);
          const pecas = res.data;
          if (pecas.some((p: any) => p.documento_id === docId)) {
            setPecasExtraidas(pecas);
            clearInterval(poll);
            clearInterval(progInterval);
            setExtractProgress(100);
            setTimeout(() => setReextrahindo(null), 1000);
            return;
          }
        } catch { /* erro silencioso */ }

        // Timeout de ~3 min: avisa mas mantém polling lento (a cada 15s) até aparecer
        if (chamadas === 36) {
          clearInterval(progInterval);
          // continua o poll — não para, só troca a velocidade
        }
        if (chamadas >= 36 && chamadas % 3 !== 0) return; // após 3 min, checa só a cada 15s

        // Desiste depois de ~6 min no total
        if (chamadas >= 72) {
          clearInterval(poll);
          setReextrahindo(null);
          alert("A extração não foi concluída. Verifique os logs do servidor ou tente novamente.");
        }
      }, 5000);

    } catch {
      alert("Erro ao acionar extração de peças.");
      setReextrahindo(null);
      setExtractProgress(0);
    }
  };

  // Ordem canônica de exibição das pastas de peças
  const TIPO_PECA_ORDER = [
    "portaria", "bo", "registro_aditamento", "relatorio_policial",
    "informacao_investigacao", "termo_declaracao", "termo_depoimento",
    "termo_interrogatorio", "auto_qualificacao", "auto_apreensao",
    "laudo_pericial", "oficio_expedido", "oficio_recebido", "requisicao",
    "mandado", "representacao", "quebra_sigilo", "extrato_financeiro",
    "despacho", "peca_processual", "certidao", "notificacao",
    "procuracao", "outro",
    // legado (migração)
    "laudo", "oficio",
  ];

  const TIPO_PECA_LABEL: Record<string, string> = {
    termo_declaracao:      "Declaração",
    termo_depoimento:      "Depoimento",
    termo_interrogatorio:  "Interrogatório",
    auto_apreensao:        "Auto de Apreensão",
    auto_qualificacao:     "Auto de Qualificação",
    oficio_expedido:       "Ofício Expedido",
    oficio_recebido:       "Ofício Recebido",
    bo:                    "Boletim de Ocorrência",
    registro_aditamento:   "Registro de Aditamento",
    portaria:              "Portaria",
    despacho:              "Despacho / Decisão",
    requisicao:            "Requisição",
    mandado:               "Mandado",
    informacao_investigacao: "Informação de Investigação",
    relatorio_policial:    "Relatório Policial",
    laudo_pericial:        "Laudo Pericial",
    quebra_sigilo:         "Quebra de Sigilo",
    extrato_financeiro:    "Extrato / Doc. Financeiro",
    representacao:         "Representação",
    certidao:              "Certidão",
    notificacao:           "Notificação",
    procuracao:            "Procuração / Substabelecimento",
    peca_processual:       "Peça Processual (MP/Juiz)",
    outro:                 "Outro",
    // legado
    laudo:  "Laudo",
    oficio: "Ofício",
  };

  const TIPO_PECA_COLOR: Record<string, string> = {
    termo_declaracao:      "bg-amber-500/10 text-amber-400 border-amber-500/20",
    termo_depoimento:      "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
    termo_interrogatorio:  "bg-orange-500/10 text-orange-400 border-orange-500/20",
    auto_apreensao:        "bg-red-500/10 text-red-400 border-red-500/20",
    auto_qualificacao:     "bg-red-700/10 text-red-300 border-red-700/20",
    oficio_expedido:       "bg-purple-500/10 text-purple-400 border-purple-500/20",
    oficio_recebido:       "bg-violet-500/10 text-violet-400 border-violet-500/20",
    bo:                    "bg-orange-500/10 text-orange-400 border-orange-500/20",
    registro_aditamento:   "bg-orange-700/10 text-orange-300 border-orange-700/20",
    portaria:              "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
    despacho:              "bg-zinc-700/50 text-zinc-400 border-zinc-600",
    requisicao:            "bg-blue-500/10 text-blue-400 border-blue-500/20",
    mandado:               "bg-rose-500/10 text-rose-400 border-rose-500/20",
    informacao_investigacao: "bg-sky-500/10 text-sky-400 border-sky-500/20",
    relatorio_policial:    "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
    laudo_pericial:        "bg-teal-500/10 text-teal-400 border-teal-500/20",
    quebra_sigilo:         "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20",
    extrato_financeiro:    "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    representacao:         "bg-pink-500/10 text-pink-400 border-pink-500/20",
    certidao:              "bg-slate-500/10 text-slate-400 border-slate-500/20",
    notificacao:           "bg-lime-500/10 text-lime-400 border-lime-500/20",
    procuracao:            "bg-stone-500/10 text-stone-400 border-stone-500/20",
    peca_processual:       "bg-indigo-700/10 text-indigo-300 border-indigo-700/20",
    outro:                 "bg-zinc-800 text-zinc-400 border-zinc-700",
    // legado
    laudo:  "bg-teal-500/10 text-teal-400 border-teal-500/20",
    oficio: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  };

  const TIPO_GERADO_LABEL: Record<string, string> = {
    relatorio_inicial: "Síntese Inicial",
    relatorio_osint_web: "Relatório OSINT Web",
    roteiro_oitiva: "Roteiro de Oitiva",
    oficio: "Ofício",
    minuta_cautelar: "Minuta Cautelar",
    relatorio: "Relatório",
    outro: "Outro",
  };

  const TIPO_GERADO_COLOR: Record<string, string> = {
    relatorio_inicial: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    relatorio_osint_web: "bg-sky-500/10 text-sky-400 border-sky-500/20",
    roteiro_oitiva: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    oficio: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    minuta_cautelar: "bg-orange-500/10 text-orange-400 border-orange-500/20",
    relatorio: "bg-green-500/10 text-green-400 border-green-500/20",
    outro: "bg-zinc-800 text-zinc-400 border-zinc-700",
  };

  if (loading) return <div className="p-8 text-zinc-500 animate-pulse">Carregando autos...</div>;
  if (!inquerito) return null;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 min-h-full flex flex-col">
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
                <button
                  onClick={() => { setNovoNumero(inquerito.numero); setEditandoNumero(true); }}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors"
                  title="Editar número do inquérito"
                >
                  <Pencil size={14} />
                </button>
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
            <ProcessosBgBadge inqId={inqId} />
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
          <OneDrivePicker onFileSelected={handleOneDriveFile} disabled={uploading} />
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

      {/* Fato Típico — compacto inline */}
      {inquerito.descricao && (
        <div className="mb-4 px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/40 flex gap-3 items-start">
          <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mt-0.5 shrink-0">Fato</span>
          <p className="text-sm text-zinc-400 leading-relaxed line-clamp-3">{inquerito.descricao}</p>
        </div>
      )}

      {/* Tabs */}
      {(() => {
        const CRIPTO_KW = ["cripto", "bitcoin", "blockchain", "ethereum", "wallet", "carteira digital", "satoshi", "nft", "defi", "binance", "metamask", "monero", "tether", "usdt"];
        const temCripto = CRIPTO_KW.some(k =>
          (inquerito.descricao || "").toLowerCase().includes(k) ||
          (inquerito.classificacao_estrategica || "").toLowerCase().includes(k)
        );
        const tabs: { id: "workspace" | "autos" | "investigacao" | "blockchain"; label: string; badge?: string }[] = [
          { id: "workspace", label: "Área de Trabalho" },
          { id: "autos", label: `Autos Físicos (${documentos.length})` },
          { id: "investigacao", label: "Investigação OSINT" },
          ...(temCripto ? [{ id: "blockchain" as const, label: "Blockchain / Cripto", badge: "auto" }] : []),
        ];
        return (
          <div className="flex gap-1 border-b border-zinc-800 mb-6 overflow-x-auto flex-shrink-0">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap flex items-center gap-1.5 ${
                  activeTab === tab.id
                    ? "border-blue-500 text-blue-400"
                    : "border-transparent text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {tab.label}
                {tab.badge && (
                  <span className="text-xs px-1 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold uppercase tracking-wider">
                    auto
                  </span>
                )}
              </button>
            ))}
          </div>
        );
      })()}

      {/* ── ABA: ÁREA DE TRABALHO ── */}
      {activeTab === "workspace" && (
        <div className="space-y-8">
          {/* Documentos Gerados pela IA */}
          <div>
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
              <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
                <Bot size={18} className="text-blue-400" /> Documentos Gerados pela IA
              </h2>
              <div className="flex items-center gap-3">
                <span className="text-sm text-zinc-500">{docsGerados.length} documento(s)</span>
                {/* Botão Síntese Inicial — aparece quando há docs indexados */}
                {documentos.some(d => d.status_processamento === "concluido" && d.tipo_peca !== "sintese_investigativa") && (
                  <button
                    onClick={() => {
                      const temRelatorio = docsGerados.some((d: any) => d.tipo === "relatorio_inicial");
                      if (temRelatorio && !confirm("Já existe uma Síntese Inicial. Deseja regenerar (apagará a atual)?")) return;
                      handleGerarRelatorioInicial(temRelatorio);
                    }}
                    disabled={gerandoRelatorio}
                    className="text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1 transition-colors disabled:opacity-50"
                    title="Gera a Síntese Inicial sobre os autos"
                  >
                    <FileText size={12} className={gerandoRelatorio ? "animate-pulse" : ""}/>
                    {gerandoRelatorio ? "Gerando síntese..." : docsGerados.some((d: any) => d.tipo === "relatorio_inicial") ? "Regenerar Síntese Inicial" : "Gerar Síntese Inicial"}
                  </button>
                )}
                <button
                  onClick={fetchDocsGerados}
                  disabled={docsGeradosLoading}
                  title="Atualizar lista"
                  className="text-zinc-600 hover:text-zinc-400 transition-colors disabled:opacity-40"
                >
                  <RefreshCw size={14} className={docsGeradosLoading ? "animate-spin" : ""} />
                </button>
              </div>
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
                {docsGerados.map((doc: any) => {
                  const processando = doc.em_processamento === true;
                  const pronto = !processando;
                  return (
                  <div key={doc.id} className={`flex items-center justify-between rounded-xl px-4 py-3 transition-colors ${
                    processando
                      ? "border border-amber-500/40 bg-amber-950/20"
                      : pronto
                        ? "border border-emerald-600/40 bg-emerald-950/10 hover:border-emerald-500/60"
                        : "border border-zinc-800 bg-zinc-900/40 hover:border-zinc-700"
                  }`}>
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className={`p-1.5 rounded border bg-zinc-950 shrink-0 ${processando ? "text-amber-400 border-amber-700/40" : pronto ? "text-emerald-400 border-emerald-700/40" : "text-blue-400 border-zinc-800"}`}>
                        {processando ? <Loader2 size={15} className="animate-spin" /> : <Bot size={15} />}
                      </div>
                      <div className="min-w-0">
                        <p className={`text-sm font-medium truncate ${processando ? "text-amber-200" : pronto ? "text-emerald-100" : "text-zinc-200"}`}>{doc.titulo}</p>
                        <p className="text-xs text-zinc-500 mt-0.5">
                          {processando
                            ? <span className="text-amber-500/80 animate-pulse">Gerando documento…</span>
                            : new Date(doc.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
                          }
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${TIPO_GERADO_COLOR[doc.tipo] || TIPO_GERADO_COLOR["outro"]}`}>
                        {TIPO_GERADO_LABEL[doc.tipo] || doc.tipo}
                      </span>
                      {processando ? (
                        <span className="flex items-center gap-1 text-xs text-amber-500/70 px-2 py-1 rounded border border-amber-700/30 cursor-not-allowed">
                          <Loader2 size={11} className="animate-spin" /> Gerando…
                        </span>
                      ) : (
                        <button onClick={() => handleAbrirDocGerado(doc)} className="flex items-center gap-1 text-xs text-zinc-400 hover:text-blue-400 px-2 py-1 rounded border border-zinc-700 hover:border-blue-500/40 transition-colors">
                          <Eye size={11} /> Ver
                        </button>
                      )}
                      <button
                        onClick={() => handleCopiarTextoLimpo(doc)}
                        disabled={processando}
                        className="p-1.5 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Copiar texto limpo (para colar no sistema)"
                        style={{ color: copiadoDocId === doc.id ? "#34d399" : "#52525b" }}
                      >
                        {copiadoDocId === doc.id ? <ClipboardCheck size={13} /> : <Copy size={13} />}
                      </button>
                      <button onClick={() => handleExportarDocGeradoPDF(doc)} disabled={processando} className="p-1.5 rounded text-zinc-600 hover:text-red-400 transition-colors disabled:opacity-30 disabled:cursor-not-allowed" title="Exportar como PDF">
                        <FileText size={13} />
                      </button>
                      <button onClick={() => handleAbrirEditDocGerado(doc)} disabled={processando} className="p-1.5 rounded text-zinc-600 hover:text-amber-400 transition-colors disabled:opacity-30 disabled:cursor-not-allowed" title="Editar documento">
                        <Pencil size={13} />
                      </button>
                      <button onClick={() => handleDeletarDocGerado(doc.id)} disabled={deletingDocGerado === doc.id} className="p-1.5 rounded text-zinc-600 hover:text-red-400 transition-colors disabled:opacity-40" title="Excluir documento">
                        {deletingDocGerado === doc.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                      </button>
                    </div>
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Consultas OSINT do Inquérito */}
          {consultasOsint.length > 0 && (
            <div>
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
                <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
                  <UserSearch size={18} className="text-purple-400" /> Consultas OSINT
                </h2>
                <span className="text-sm text-zinc-500">{consultasOsint.length} alvo(s)</span>
              </div>
              <div className="space-y-2">
                {consultasOsint.map((grupo: any) => {
                  const aberto = osintAbertos[grupo.documento_hash] ?? false;
                  const modOk = grupo.modulos.filter((m: any) => m.status === "ok");
                  const modErro = grupo.modulos.filter((m: any) => m.status !== "ok");
                  return (
                    <div key={grupo.documento_hash} className="border border-zinc-800 rounded-xl bg-zinc-900/40 overflow-hidden">
                      <button
                        onClick={() => setOsintAbertos(p => ({ ...p, [grupo.documento_hash]: !aberto }))}
                        className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-800/40 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <div className="p-1.5 rounded border bg-zinc-950 text-purple-400 border-zinc-800">
                            <UserSearch size={14} />
                          </div>
                          <div className="text-left">
                            <p className="text-sm font-medium text-zinc-200">{grupo.nome || <span className="text-zinc-500 italic">Alvo sem identificação</span>}</p>
                            <p className="text-xs text-zinc-500 mt-0.5">
                              {grupo.modulos.length} módulo(s) · {modOk.length} ok · {new Date(grupo.ultima_consulta).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {modErro.length > 0 && (
                            <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full" title={modErro.map((m: any) => `${m.tipo}: ${m.status}`).join(" | ")}>
                              {modErro.length} falha{modErro.length > 1 ? "s" : ""}
                            </span>
                          )}
                          <ChevronDown size={14} className={`text-zinc-500 transition-transform ${aberto ? "rotate-180" : ""}`} />
                        </div>
                      </button>
                      {aberto && (
                        <div className="border-t border-zinc-800 px-4 py-3 space-y-1">
                          {grupo.modulos.map((m: any, i: number) => (
                            <div key={i} className="flex items-center justify-between text-xs py-1">
                              <span className={m.status === "ok" ? "text-zinc-300" : "text-zinc-600"}>{m.tipo}</span>
                              <span className={`px-2 py-0.5 rounded-full border text-xs ${
                                m.status === "ok" ? "border-green-700/40 text-green-400 bg-green-500/5"
                                : m.status === "timeout" ? "border-amber-700/40 text-amber-400 bg-amber-500/5"
                                : "border-red-700/40 text-red-400 bg-red-500/5"
                              }`}>
                                {m.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Agente Sherlock ── */}
          <div>
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
              <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
                <Microscope size={18} className="text-violet-400" /> Agente Sherlock
                <span className="text-xs font-normal text-zinc-500 ml-1">— análise estratégica em 5 camadas</span>
              </h2>
              <div className="flex items-center gap-2">
                {sherlockAnalise && (
                  <button
                    onClick={() => handleSherlock(true)}
                    disabled={sherlockLoading}
                    title="Forçar regeneração"
                    className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition-colors disabled:opacity-40"
                  >
                    <RefreshCw size={12} className={sherlockLoading ? "animate-spin" : ""} /> Regenerar
                  </button>
                )}
                <button
                  onClick={() => handleSherlock(false)}
                  disabled={sherlockLoading}
                  className="flex items-center gap-1.5 text-xs bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                >
                  {sherlockLoading
                    ? <><Loader2 size={12} className="animate-spin" /> Analisando...</>
                    : <><Microscope size={12} /> {sherlockAnalise ? "Ver análise" : "Acionar Sherlock"}</>
                  }
                </button>
              </div>
            </div>

            {sherlockErro && (
              <div className="flex items-start gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-4">
                <AlertCircle size={15} className="shrink-0 mt-0.5" />
                <span>{sherlockErro}</span>
              </div>
            )}

            {sherlockLoading && !sherlockAnalise && (
              <div className="py-14 text-center text-zinc-500 border border-zinc-800 border-dashed rounded-xl bg-zinc-900/40">
                <Loader2 className="w-10 h-10 mx-auto mb-3 opacity-40 animate-spin text-violet-400" />
                <p className="font-medium text-zinc-400">Sherlock está raciocinando...</p>
                <p className="text-sm mt-1 text-zinc-600">Cruzando contradições · tipicidade · diligências · tese · advogado do diabo</p>
              </div>
            )}

            {!sherlockAnalise && !sherlockLoading && !sherlockErro && (
              <div className="py-10 text-center text-zinc-600 border border-zinc-800 border-dashed rounded-xl bg-zinc-900/40">
                <Microscope className="w-10 h-10 mx-auto mb-3 opacity-20" />
                <p className="font-medium">Análise estratégica não gerada.</p>
                <p className="text-sm mt-1 text-zinc-700 max-w-sm mx-auto">
                  Acione o Sherlock após ter o Relatório Inicial. Quanto mais dados (OSINT, fichas, síntese), melhor a análise.
                </p>
              </div>
            )}

            {sherlockAnalise && (
              <div className="space-y-3">
                {/* Aviso de análise incompleta (JSON truncado) */}
                {sherlockAnalise._erro && (
                  <div className="flex items-start gap-2 text-sm text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3">
                    <AlertCircle size={15} className="shrink-0 mt-0.5" />
                    <span>{sherlockAnalise._erro}</span>
                  </div>
                )}
                {/* Resumo executivo */}
                <div className="bg-violet-500/5 border border-violet-500/20 rounded-xl px-5 py-4">
                  <p className="text-sm font-semibold text-violet-300 mb-1 flex items-center gap-1.5">
                    <Sparkles size={13} /> Resumo Estratégico
                  </p>
                  <p className="text-sm text-zinc-300 leading-relaxed">{sherlockAnalise.resumo_executivo}</p>
                  {sherlockAnalise.recomendacao_final && (
                    <div className="mt-3 pt-3 border-t border-violet-500/10">
                      <p className="text-xs font-semibold text-amber-400 mb-0.5">Ação prioritária para hoje:</p>
                      <p className="text-sm text-amber-200">{sherlockAnalise.recomendacao_final}</p>
                    </div>
                  )}
                </div>

                {/* Crimes */}
                {sherlockAnalise.crimes_identificados?.length > 0 && (
                  <div className="border border-zinc-800 rounded-xl overflow-hidden">
                    <button
                      onClick={() => setSherlockSecaoAberta(v => v === "crimes" ? null : "crimes")}
                      className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-800/40 transition-colors"
                    >
                      <span className="flex items-center gap-2"><Scale size={14} className="text-blue-400" /> Tipificação Penal ({sherlockAnalise.crimes_identificados.length})</span>
                      {sherlockSecaoAberta === "crimes" ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    {sherlockSecaoAberta === "crimes" && (
                      <div className="border-t border-zinc-800 divide-y divide-zinc-800/60">
                        {sherlockAnalise.crimes_identificados.map((c: any, i: number) => (
                          <div key={i} className="px-4 py-3 flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-medium text-zinc-200">{c.tipo}</p>
                              <p className="text-xs text-zinc-500 mt-0.5">{c.artigo}</p>
                              {c.observacao && <p className="text-xs text-zinc-600 mt-1 italic">{c.observacao}</p>}
                            </div>
                            <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${
                              c.fase_prova === "materialidade provada" ? "bg-green-500/10 text-green-400 border-green-500/20"
                              : c.fase_prova === "indiciária" ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                              : "bg-red-500/10 text-red-400 border-red-500/20"
                            }`}>{c.fase_prova}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Contradições */}
                {sherlockAnalise.contradicoes?.length > 0 && (
                  <div className="border border-zinc-800 rounded-xl overflow-hidden">
                    <button
                      onClick={() => setSherlockSecaoAberta(v => v === "contradicoes" ? null : "contradicoes")}
                      className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-800/40 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <ShieldAlert size={14} className="text-red-400" /> Contradições ({sherlockAnalise.contradicoes.length})
                        {sherlockAnalise.contradicoes.some((c: any) => c.gravidade === "CRÍTICA") && (
                          <span className="text-xs bg-red-500/10 text-red-400 border border-red-500/20 px-1.5 py-0.5 rounded-full">críticas</span>
                        )}
                      </span>
                      {sherlockSecaoAberta === "contradicoes" ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    {sherlockSecaoAberta === "contradicoes" && (
                      <div className="border-t border-zinc-800 divide-y divide-zinc-800/60">
                        {sherlockAnalise.contradicoes.map((c: any, i: number) => (
                          <div key={i} className="px-4 py-3">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded-full border ${
                                c.gravidade === "CRÍTICA" ? "bg-red-500/10 text-red-400 border-red-500/20"
                                : c.gravidade === "RELEVANTE" ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                : "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                              }`}>{c.gravidade}</span>
                            </div>
                            <p className="text-sm text-zinc-300">{c.descricao}</p>
                            <div className="mt-1.5 grid grid-cols-2 gap-2 text-xs text-zinc-500">
                              <span className="bg-zinc-800/60 px-2 py-1 rounded">A: {c.fonte_a}</span>
                              <span className="bg-zinc-800/60 px-2 py-1 rounded">B: {c.fonte_b}</span>
                            </div>
                            {c.impacto && <p className="text-xs text-zinc-500 mt-1.5 italic">{c.impacto}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Checklist de tipicidade */}
                {sherlockAnalise.checklist_tipicidade?.length > 0 && (
                  <div className="border border-zinc-800 rounded-xl overflow-hidden">
                    <button
                      onClick={() => setSherlockSecaoAberta(v => v === "tipicidade" ? null : "tipicidade")}
                      className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-800/40 transition-colors"
                    >
                      <span className="flex items-center gap-2"><ListChecks size={14} className="text-cyan-400" /> Checklist de Tipicidade ({sherlockAnalise.checklist_tipicidade.length} elementares)</span>
                      {sherlockSecaoAberta === "tipicidade" ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    {sherlockSecaoAberta === "tipicidade" && (
                      <div className="border-t border-zinc-800 divide-y divide-zinc-800/60">
                        {sherlockAnalise.checklist_tipicidade.map((el: any, i: number) => (
                          <div key={i} className="px-4 py-3 flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-zinc-300">{el.elementar}</p>
                              <p className="text-xs text-zinc-600 mt-0.5">{el.artigo}</p>
                              {el.prova_suporte && <p className="text-xs text-zinc-500 mt-1 italic">{el.prova_suporte}</p>}
                            </div>
                            <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${
                              el.status === "PROVADO" ? "bg-green-500/10 text-green-400 border-green-500/20"
                              : el.status === "INDICIÁRIO" ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                              : el.status === "CONTRADITÓRIO" ? "bg-red-500/10 text-red-400 border-red-500/20"
                              : "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                            }`}>{el.status === "PROVADO" ? "✓ " : el.status === "INDICIÁRIO" ? "△ " : el.status === "AUSENTE" ? "✗ " : "⚡ "}{el.status}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Backlog de diligências */}
                {sherlockAnalise.backlog_diligencias?.length > 0 && (
                  <div className="border border-zinc-800 rounded-xl overflow-hidden">
                    <button
                      onClick={() => setSherlockSecaoAberta(v => v === "backlog" ? null : "backlog")}
                      className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-800/40 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <ListChecks size={14} className="text-amber-400" /> Backlog de Diligências ({sherlockAnalise.backlog_diligencias.length})
                        {sherlockAnalise.backlog_diligencias.filter((d: any) => d.urgencia === "URGENTE").length > 0 && (
                          <span className="text-xs bg-red-500/10 text-red-400 border border-red-500/20 px-1.5 py-0.5 rounded-full">
                            {sherlockAnalise.backlog_diligencias.filter((d: any) => d.urgencia === "URGENTE").length} urgentes
                          </span>
                        )}
                      </span>
                      {sherlockSecaoAberta === "backlog" ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    {sherlockSecaoAberta === "backlog" && (
                      <div className="border-t border-zinc-800 divide-y divide-zinc-800/60">
                        {sherlockAnalise.backlog_diligencias.map((d: any, i: number) => (
                          <div key={i} className="px-4 py-3">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded-full border ${
                                d.urgencia === "URGENTE" ? "bg-red-500/10 text-red-400 border-red-500/20"
                                : d.urgencia === "IMPRESCINDÍVEL" ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                              }`}>{d.urgencia}</span>
                              {d.prazo_sugerido && d.prazo_sugerido !== "sem prazo fixo" && (
                                <span className="text-xs text-zinc-500">{d.prazo_sugerido}</span>
                              )}
                            </div>
                            <p className="text-sm text-zinc-300">{d.descricao}</p>
                            {d.justificativa && <p className="text-xs text-zinc-500 mt-1">{d.justificativa}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Tese de autoria */}
                {sherlockAnalise.tese_autoria && (
                  <div className="border border-zinc-800 rounded-xl overflow-hidden">
                    <button
                      onClick={() => setSherlockSecaoAberta(v => v === "tese" ? null : "tese")}
                      className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-800/40 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <Network size={14} className="text-green-400" /> Tese de Autoria e Materialidade
                        <span className={`text-xs px-2 py-0.5 rounded-full border ${
                          sherlockAnalise.tese_autoria.grau_certeza === "ALTO" ? "bg-green-500/10 text-green-400 border-green-500/20"
                          : sherlockAnalise.tese_autoria.grau_certeza === "MÉDIO" ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                          : "bg-red-500/10 text-red-400 border-red-500/20"
                        }`}>certeza {sherlockAnalise.tese_autoria.grau_certeza}</span>
                      </span>
                      {sherlockSecaoAberta === "tese" ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    {sherlockSecaoAberta === "tese" && (
                      <div className="border-t border-zinc-800 px-4 py-4 space-y-4">
                        <div>
                          <p className="text-xs font-semibold text-zinc-500 uppercase mb-1">Hipótese central</p>
                          <p className="text-sm text-zinc-300 leading-relaxed">{sherlockAnalise.tese_autoria.hipotese_central}</p>
                        </div>
                        {sherlockAnalise.tese_autoria.justificativa_certeza && (
                          <div>
                            <p className="text-xs font-semibold text-zinc-500 uppercase mb-1">Grau de certeza — justificativa</p>
                            <p className="text-sm text-zinc-400">{sherlockAnalise.tese_autoria.justificativa_certeza}</p>
                          </div>
                        )}
                        {sherlockAnalise.tese_autoria.cadeia_provas?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-zinc-500 uppercase mb-2">Cadeia de provas</p>
                            <ol className="space-y-1 list-decimal list-inside">
                              {sherlockAnalise.tese_autoria.cadeia_provas.map((p: string, i: number) => (
                                <li key={i} className="text-sm text-zinc-300">{p}</li>
                              ))}
                            </ol>
                          </div>
                        )}
                        {sherlockAnalise.tese_autoria.papel_por_pessoa?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-zinc-500 uppercase mb-2">Papel de cada pessoa</p>
                            <div className="space-y-2">
                              {sherlockAnalise.tese_autoria.papel_por_pessoa.map((p: any, i: number) => (
                                <div key={i} className="flex items-start gap-2 text-sm">
                                  <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 mt-0.5 ${
                                    p.papel === "AUTOR PRINCIPAL" ? "bg-red-500/10 text-red-400 border-red-500/20"
                                    : p.papel === "COAUTOR" ? "bg-orange-500/10 text-orange-400 border-orange-500/20"
                                    : p.papel === "PARTÍCIPE" ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                    : p.papel === "VÍTIMA" ? "bg-blue-500/10 text-blue-400 border-blue-500/20"
                                    : p.papel === "TESTEMUNHA" ? "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                                    : "bg-zinc-800 text-zinc-500 border-zinc-700"
                                  }`}>{p.papel}</span>
                                  <div>
                                    <span className="font-medium text-zinc-200">{p.nome}</span>
                                    {p.fundamento && <span className="text-zinc-500 ml-1">— {p.fundamento}</span>}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Advogado do Diabo */}
                {sherlockAnalise.advogado_diabo && (
                  <div className="border border-zinc-800 rounded-xl overflow-hidden">
                    <button
                      onClick={() => setSherlockSecaoAberta(v => v === "diabo" ? null : "diabo")}
                      className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-800/40 transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <Swords size={14} className="text-orange-400" /> Advogado do Diabo
                        {sherlockAnalise.advogado_diabo.vulnerabilidades?.some((v: any) => v.gravidade === "ALTA") && (
                          <span className="text-xs bg-orange-500/10 text-orange-400 border border-orange-500/20 px-1.5 py-0.5 rounded-full">vulnerabilidades altas</span>
                        )}
                      </span>
                      {sherlockSecaoAberta === "diabo" ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    {sherlockSecaoAberta === "diabo" && (
                      <div className="border-t border-zinc-800 px-4 py-4 space-y-4">
                        {sherlockAnalise.advogado_diabo.ponto_mais_fragil && (
                          <div className="bg-orange-500/5 border border-orange-500/15 rounded-lg px-3 py-2">
                            <p className="text-xs font-semibold text-orange-400 mb-0.5">Elo mais fraco da tese:</p>
                            <p className="text-sm text-zinc-300">{sherlockAnalise.advogado_diabo.ponto_mais_fragil}</p>
                          </div>
                        )}
                        {sherlockAnalise.advogado_diabo.pior_cenario && (
                          <div>
                            <p className="text-xs font-semibold text-zinc-500 uppercase mb-1">Pior cenário processual</p>
                            <p className="text-sm text-zinc-400">{sherlockAnalise.advogado_diabo.pior_cenario}</p>
                          </div>
                        )}
                        {sherlockAnalise.advogado_diabo.vulnerabilidades?.length > 0 && (
                          <div className="space-y-3">
                            <p className="text-xs font-semibold text-zinc-500 uppercase">Vulnerabilidades ({sherlockAnalise.advogado_diabo.vulnerabilidades.length})</p>
                            {sherlockAnalise.advogado_diabo.vulnerabilidades.map((v: any, i: number) => (
                              <div key={i} className="border border-zinc-800 rounded-lg px-3 py-3">
                                <div className="flex items-center gap-2 mb-1.5">
                                  <span className={`text-xs px-2 py-0.5 rounded-full border ${
                                    v.gravidade === "ALTA" ? "bg-red-500/10 text-red-400 border-red-500/20"
                                    : v.gravidade === "MÉDIA" ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                    : "bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                                  }`}>{v.gravidade}</span>
                                  <span className="text-xs text-zinc-500">{v.tipo}</span>
                                </div>
                                <p className="text-sm text-zinc-300 mb-2">{v.descricao}</p>
                                {v.contramedida && (
                                  <div className="bg-green-500/5 border border-green-500/15 rounded px-2 py-1.5">
                                    <p className="text-xs font-semibold text-green-400 mb-0.5">Contramedida:</p>
                                    <p className="text-xs text-zinc-400">{v.contramedida}</p>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                <p className="text-xs text-zinc-600 text-right">
                  gerado em {sherlockAnalise._gerado_em ? new Date(sherlockAnalise._gerado_em).toLocaleString("pt-BR") : "—"}
                  {sherlockAnalise._modelo && ` · ${sherlockAnalise._modelo}`}
                </p>
              </div>
            )}
          </div>

          {/* Peças Individuais Extraídas */}
          <div>
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
              <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
                <FileText size={18} className="text-amber-400" /> Peças Individuais Extraídas
              </h2>
              <span className="text-sm text-zinc-500">{pecasExtraidas.length} peça(s)</span>
            </div>
            {pecasLoading ? (
              <div className="flex items-center gap-2 text-zinc-500 py-6">
                <Loader2 size={16} className="animate-spin" /> Carregando peças extraídas...
              </div>
            ) : pecasExtraidas.length === 0 ? (
              <div className="py-10 text-center text-zinc-600 border border-zinc-800 border-dashed rounded-xl bg-zinc-900/40">
                <FileText className="w-10 h-10 mx-auto mb-3 opacity-20" />
                <p className="font-medium">Nenhuma peça extraída ainda.</p>
                <p className="text-sm mt-1 text-zinc-700 max-w-sm mx-auto">
                  As peças são extraídas automaticamente após a ingestão. Para documentos já importados, use o botão "Extrair peças" na aba Autos.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {pecasExtraidas.map((peca: any) => (
                  <div key={peca.id} className="flex items-center justify-between border border-zinc-800 rounded-xl px-4 py-3 bg-zinc-900/40 hover:border-zinc-700 transition-colors">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className="p-1.5 rounded border bg-zinc-950 text-amber-400 border-zinc-800 shrink-0">
                        <FileText size={14} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-zinc-200 truncate">{peca.titulo}</p>
                        <p className="text-xs text-zinc-500 mt-0.5">
                          {peca.documento_nome && <span className="mr-2 opacity-60">{peca.documento_nome}</span>}
                          {peca.pagina_inicial != null && (
                            <span>fls. {peca.pagina_inicial}{peca.pagina_final && peca.pagina_final !== peca.pagina_inicial ? `–${peca.pagina_final}` : ""}</span>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${TIPO_PECA_COLOR[peca.tipo] || TIPO_PECA_COLOR["outro"]}`}>
                        {TIPO_PECA_LABEL[peca.tipo] || peca.tipo}
                      </span>
                      <button
                        onClick={() => handleAbrirPecaNoPDF(peca)}
                        title="Abrir PDF original"
                        className="flex items-center gap-1 text-xs text-zinc-400 hover:text-blue-400 px-2 py-1 rounded border border-zinc-700 hover:border-blue-500/40 transition-colors"
                      >
                        <Eye size={11} /> PDF
                      </button>
                      <button
                        onClick={() => handleAbrirPeca(peca)}
                        title="Ver texto extraído"
                        className="flex items-center gap-1 text-xs text-zinc-500 hover:text-amber-400 px-2 py-1 rounded border border-zinc-700 hover:border-amber-500/40 transition-colors"
                      >
                        <FileText size={11} /> Texto
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── ABA: AUTOS FÍSICOS ── */}
      {activeTab === "autos" && (
        <div className="space-y-4">
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
              {documentos.some(d => d.status_processamento === "concluido" && d.tipo_peca !== "sintese_investigativa") && (
                <button
                  onClick={handleCatalogarPecas}
                  disabled={catalogando}
                  className="text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1 transition-colors disabled:opacity-50"
                >
                  <FileText size={12} className={catalogando ? "animate-pulse" : ""}/>
                  {catalogando ? "Catalogando..." : "Catalogar peças"}
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
                  const pecasDoDoc = pecasExtraidas.filter((p: any) => p.documento_id === doc.id);
                  return (
                    <div key={doc.id} className={`flex flex-col rounded-lg border transition-colors ${isSintetico ? "bg-blue-500/5 border-blue-500/20" : "bg-zinc-900/60 border-zinc-800"}`}>
                      {/* Cabeçalho do documento */}
                      <div
                        onClick={() => handleAbrirDoc(doc)}
                        className={`flex justify-between items-center p-3 cursor-pointer rounded-lg ${isSintetico ? "hover:border-blue-500/40" : "hover:bg-zinc-800/60"} transition-colors`}
                      >
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
                          {doc.status_processamento === "concluido" && !isSintetico && (
                            <span
                              title={pecasDoDoc.length > 0 ? `${pecasDoDoc.length} peça(s) catalogada(s)` : "Aguardando catalogação de peças"}
                              className={`w-2 h-2 rounded-full shrink-0 ${pecasDoDoc.length > 0 ? "bg-green-400" : "bg-amber-400 animate-pulse"}`}
                            />
                          )}
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
                          {!isSintetico && (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDeletarDoc(doc.id, doc.nome_arquivo); }}
                              disabled={deletingDoc === doc.id}
                              title="Excluir documento"
                              className="p-1 rounded text-zinc-700 hover:text-red-400 transition-colors disabled:opacity-40"
                            >
                              {deletingDoc === doc.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Barra de progresso de extração */}
                      {reextrahindo === doc.id && (
                        <div className="mx-3 mb-3 animate-in fade-in slide-in-from-top-1">
                          <div className="flex justify-between items-center mb-1 w-full">
                            <span className="text-xs text-zinc-500 uppercase tracking-widest font-semibold flex items-center gap-1">
                              <Loader2 size={10} className="animate-spin text-amber-500"/>
                              Acelerador Neuronal em uso
                            </span>
                            <span className="text-xs text-zinc-500 font-mono">{extractProgress}%</span>
                          </div>
                          <div className="h-1 bg-zinc-950/80 rounded-full overflow-hidden w-full border border-black/50">
                            <div
                              className="h-full bg-gradient-to-r from-amber-500 to-amber-300 rounded-full transition-all duration-500 ease-out"
                              style={{ width: `${extractProgress}%` }}
                            />
                          </div>
                        </div>
                      )}

                      {/* Peças extraídas deste documento */}
                      {pecasDoDoc.length > 0 && (
                        <div className="border-t border-zinc-800/60 divide-y divide-zinc-800/40">
                          {pecasDoDoc.map((peca: any) => (
                            <div key={peca.id} className="flex items-center justify-between px-3 py-2 hover:bg-zinc-800/30 transition-colors">
                              <div className="flex items-center gap-2 min-w-0 flex-1">
                                <span className="text-xs text-zinc-600 font-mono shrink-0 w-14 text-right">
                                  {peca.pagina_inicial != null
                                    ? `fls. ${peca.pagina_inicial}${peca.pagina_final && peca.pagina_final !== peca.pagina_inicial ? `–${peca.pagina_final}` : ""}`
                                    : ""}
                                </span>
                                <span className="text-xs text-zinc-300 truncate">{peca.titulo}</span>
                                {peca.tipo && (
                                  <span className={`text-xs px-1.5 py-0.5 rounded-full border shrink-0 ${TIPO_PECA_COLOR[peca.tipo] || TIPO_PECA_COLOR["outro"]}`}>
                                    {TIPO_PECA_LABEL[peca.tipo] || peca.tipo}
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-1 shrink-0 ml-2">
                                <button
                                  onClick={(e) => { e.stopPropagation(); handleAbrirPecaNoPDF(peca); }}
                                  title="Abrir PDF original"
                                  className="flex items-center gap-1 text-xs text-zinc-500 hover:text-blue-400 px-2 py-1 rounded border border-zinc-800 hover:border-blue-500/40 transition-colors"
                                >
                                  <Eye size={10}/> PDF
                                </button>
                                <button
                                  onClick={(e) => { e.stopPropagation(); handleAbrirPeca(peca); }}
                                  title="Ver texto extraído"
                                  className="flex items-center gap-1 text-xs text-zinc-500 hover:text-amber-400 px-2 py-1 rounded border border-zinc-800 hover:border-amber-500/40 transition-colors"
                                >
                                  <FileText size={10}/> Texto
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                };

                return (
                  <>
                    {/* Síntese sempre no topo */}
                    {sintese && renderDocCard(sintese)}

                    {/* Grupos por tipo de peça — ordem canônica */}
                    {[
                      ...TIPO_PECA_ORDER.filter(t => grupos[t]),
                      ...Object.keys(grupos).filter(t => !TIPO_PECA_ORDER.includes(t)),
                    ].map(tipo => {
                      const docs = grupos[tipo];
                      if (!docs) return null;
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
      )}

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
                      <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-400">
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

      {/* ── ABA: INVESTIGAÇÃO OSINT ── */}
      {activeTab === "investigacao" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
            <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
              <UserSearch size={18} className="text-purple-400" /> Investigação OSINT
            </h2>
          </div>
          <PainelInvestigacao inqueritoId={inqId} />
        </div>
      )}

      {/* ── ABA: BLOCKCHAIN / CRIPTO ── */}
      {activeTab === "blockchain" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-4">
            <h2 className="text-xl font-semibold text-zinc-200 flex items-center gap-2">
              <Network size={18} className="text-cyan-400" /> Análise Blockchain / Cripto
            </h2>
            <span className="text-xs px-2 py-1 rounded-full border border-cyan-500/30 text-cyan-400 bg-cyan-500/5 font-bold uppercase tracking-wider">
              Detectado automaticamente
            </span>
          </div>

          {/* Aviso de detecção */}
          <div className="flex gap-3 p-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5">
            <Network size={16} className="text-cyan-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-cyan-300 font-medium mb-1">Conteúdo cripto/blockchain identificado neste inquérito</p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                O Escrivão AI detectou termos relacionados a criptoativos na descrição deste IP.
                Use o Copiloto Investigativo (Ctrl+Space) com o comando{" "}
                <code className="text-cyan-400 bg-zinc-900 px-1 rounded text-xs">/analisar carteira &lt;endereço&gt;</code>{" "}
                para rastreio on-chain, análise de risco e identificação de exchanges.
              </p>
            </div>
          </div>

          {/* Busca rápida de carteira */}
          <div className="space-y-3">
            <p className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Busca rápida de carteira</p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" size={14} />
                <input
                  id="blockchain-wallet-input"
                  type="text"
                  placeholder="Cole o endereço da carteira (BTC, ETH, etc.)"
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-4 h-11 text-sm text-zinc-300 placeholder-zinc-700 focus:outline-none focus:border-cyan-500/40 font-mono"
                />
              </div>
              <button
                onClick={() => {
                  const el = document.getElementById("blockchain-wallet-input") as HTMLInputElement | null;
                  const addr = el?.value?.trim();
                  setCopilotoOpen(true);
                  if (addr) {
                    setTimeout(() => {
                      const evt = new CustomEvent("copiloto:prefill", { detail: `/analisar carteira ${addr}` });
                      window.dispatchEvent(evt);
                    }, 300);
                  }
                }}
                className="px-4 h-11 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-sm font-semibold hover:bg-cyan-500/20 transition-colors whitespace-nowrap"
              >
                Analisar no Copiloto
              </button>
            </div>
          </div>

          {/* Capacidades disponíveis */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { icon: "🔗", titulo: "Rastreio on-chain", desc: "Mapeamento de transações em Bitcoin, Ethereum e redes compatíveis." },
              { icon: "⚠️", titulo: "Score de risco", desc: "Identificação de carteiras associadas a darknet, ransomware e fraudes." },
              { icon: "🏦", titulo: "Identificação de exchanges", desc: "Detecção de exchanges KYC para solicitação de dados do titular." },
              { icon: "📊", titulo: "Fluxo de fundos", desc: "Visualização do caminho dos ativos entre carteiras e serviços." },
            ].map(item => (
              <div key={item.titulo} className="flex gap-3 p-4 rounded-xl border border-zinc-800 bg-zinc-900/40">
                <span className="text-xl shrink-0">{item.icon}</span>
                <div>
                  <p className="text-sm font-semibold text-zinc-200 mb-0.5">{item.titulo}</p>
                  <p className="text-xs text-zinc-500 leading-relaxed">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

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

      {/* Modal de visualização de documento gerado — Portal para escapar de stacking contexts */}
      {docGeradoViewer.open && typeof window !== "undefined" && createPortal(
        <>
          <style>{`
            .doc-viewer b, .doc-viewer strong { color: #e4e4e7; font-weight: 600; }
            .doc-viewer i, .doc-viewer em { color: #a1a1aa; font-style: italic; }
            .doc-viewer code { background: #18181b; border: 1px solid #3f3f46; padding: 1px 6px; border-radius: 4px; font-family: monospace; font-size: 0.8em; color: #d4d4d8; }
            .doc-viewer pre { background: #18181b; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px 12px; overflow-x: auto; margin: 6px 0; }
            .doc-viewer a { color: #60a5fa; text-decoration: underline; }
          `}</style>
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setDocGeradoViewer(v => ({ ...v, open: false }))}>
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
                  /<[a-zA-Z][^>]*>/.test(docGeradoViewer.conteudo) ? (
                    <div
                      className="doc-viewer text-zinc-300 text-sm leading-7"
                      dangerouslySetInnerHTML={{ __html: docGeradoViewer.conteudo.replace(/\n/g, "<br/>") }}
                    />
                  ) : (
                    <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {docGeradoViewer.conteudo}
                      </ReactMarkdown>
                    </div>
                  )
                ) : (
                  <div className="text-center py-16 text-zinc-500">
                    <Bot size={32} className="mx-auto mb-3 opacity-30" />
                    <p>Conteúdo não disponível.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>,
        document.body
      )}

      {/* Modal de edição de documento gerado */}
      {editDocGerado?.open && typeof window !== "undefined" && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setEditDocGerado(null)}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl mx-4" onClick={e => e.stopPropagation()}>
            {/* Cabeçalho */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <Pencil size={16} className="text-amber-400 shrink-0" />
                <input
                  className="flex-1 bg-transparent text-sm font-semibold text-zinc-100 outline-none border-b border-zinc-700 focus:border-amber-500 pb-0.5 min-w-0 transition-colors"
                  value={editDocGerado.titulo}
                  onChange={e => setEditDocGerado(prev => prev ? { ...prev, titulo: e.target.value } : null)}
                  placeholder="Título do documento"
                />
              </div>
              <button onClick={() => setEditDocGerado(null)} className="ml-4 p-1.5 rounded text-zinc-500 hover:text-zinc-200 transition-colors shrink-0">
                <X size={16} />
              </button>
            </div>
            {/* Editor */}
            <div className="flex-1 overflow-hidden px-6 py-4 min-h-0">
              <textarea
                className="w-full h-full min-h-[400px] bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-200 font-mono leading-relaxed resize-none outline-none focus:border-amber-500/50 transition-colors"
                value={editDocGerado.conteudo}
                onChange={e => setEditDocGerado(prev => prev ? { ...prev, conteudo: e.target.value } : null)}
                spellCheck={false}
              />
            </div>
            {/* Rodapé */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-800 shrink-0">
              <p className="text-xs text-zinc-600">{editDocGerado.conteudo.length.toLocaleString()} caracteres</p>
              <div className="flex gap-2">
                <button onClick={() => setEditDocGerado(null)} className="px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 rounded-lg transition-colors">
                  Cancelar
                </button>
                <button
                  onClick={handleSalvarEditDocGerado}
                  disabled={editDocGerado.saving}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30 hover:bg-amber-500/20 rounded-lg transition-colors disabled:opacity-50"
                >
                  {editDocGerado.saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                  {editDocGerado.saving ? "Salvando..." : "Salvar alterações"}
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Modal de visualização de peça extraída */}
      {pecaViewer.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setPecaViewer(v => ({ ...v, open: false }))}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl mx-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <FileText size={18} className="text-amber-400 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-100 truncate">{pecaViewer.peca?.titulo}</p>
                  <p className="text-xs text-zinc-500">
                    {TIPO_PECA_LABEL[pecaViewer.peca?.tipo] || pecaViewer.peca?.tipo}
                    {pecaViewer.peca?.documento_nome && ` · ${pecaViewer.peca.documento_nome}`}
                    {pecaViewer.peca?.pagina_inicial != null && ` · fls. ${pecaViewer.peca.pagina_inicial}${pecaViewer.peca.pagina_final && pecaViewer.peca.pagina_final !== pecaViewer.peca.pagina_inicial ? `–${pecaViewer.peca.pagina_final}` : ""}`}
                  </p>
                </div>
              </div>
              <button onClick={() => setPecaViewer(v => ({ ...v, open: false }))} className="text-zinc-500 hover:text-zinc-300 p-1 transition-colors ml-4 shrink-0">
                <X size={18} />
              </button>
            </div>
            {pecaViewer.peca?.resumo && (
              <div className="px-6 pt-4 pb-0">
                <p className="text-xs text-zinc-500 bg-zinc-800/60 border border-zinc-700/40 rounded-lg px-3 py-2 leading-relaxed italic">{pecaViewer.peca.resumo}</p>
              </div>
            )}
            <div className="overflow-y-auto flex-1 px-6 py-4">
              {pecaViewer.loading ? (
                <div className="flex items-center justify-center py-16 text-zinc-500">
                  <Loader2 size={24} className="animate-spin mr-2" /> Carregando peça...
                </div>
              ) : pecaViewer.peca?.conteudo_texto ? (
                <div className="text-sm text-zinc-300 leading-relaxed font-sans selection:bg-amber-500/20">
                  {pecaViewer.peca.conteudo_texto.split(/(?:\r?\n\s*){2,}/).map((para: string, i: number) => (
                    <p key={i} className="mb-4 text-justify">
                      {para.replace(/\r?\n/g, ' ')}
                    </p>
                  ))}
                </div>
              ) : (
                <div className="text-center py-16 text-zinc-500">
                  <FileText size={32} className="mx-auto mb-3 opacity-30" />
                  <p>Conteúdo não disponível.</p>
                </div>
              )}
            </div>
            {pecaViewer.peca?.conteudo_texto && (
              <div className="px-6 py-3 border-t border-zinc-800 text-xs text-zinc-600 shrink-0">
                {pecaViewer.peca.conteudo_texto.length.toLocaleString()} caracteres
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal de visualização de documento */}
      {/* PDF Viewer — abre PDF na página da peça */}
      {pdfViewer.open && pdfViewer.url && (
        <PDFViewer
          url={pdfViewer.url}
          initialPage={pdfViewer.page}
          titulo={pdfViewer.titulo}
          onClose={closePdfViewer}
        />
      )}
      {pdfViewer.open && !pdfViewer.url && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 backdrop-blur-sm">
          <div className="flex items-center gap-3 text-zinc-400 bg-zinc-900 border border-zinc-700 rounded-xl px-6 py-4">
            <Loader2 size={20} className="animate-spin text-blue-400" />
            <span className="text-sm">Carregando PDF...</span>
          </div>
        </div>
      )}

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
