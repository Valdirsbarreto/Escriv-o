"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAppStore } from "@/store/app";
import { api } from "@/lib/api";
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
import { FolderOpen, ArrowLeft, Upload, FileText, CheckCircle2, FileType2, Trash2, RefreshCw, Sparkles, Loader2, AlertCircle, Pencil, X, Check, CalendarPlus, Clock, MapPin, ExternalLink } from "lucide-react";
import { IntimacaoUploadModal } from "@/components/IntimacaoUploadModal";

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
  const MAX_POLLS_IDLE = 40; // ~2min sem progresso → para de pedir síntese automaticamente

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
      // Se todos os docs concluídos mas síntese não pronta, conta polls ociosos
      if (data.processando === 0 && data.pendentes === 0 && !data.sintese_pronta) {
        pollCount.current += 1;
        if (pollCount.current >= MAX_POLLS_IDLE) {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
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
  const { setInqueritoAtivoId, setCopilotoOpen } = useAppStore();

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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sintesePollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  if (loading) return <div className="p-8 text-zinc-500 animate-pulse">Carregando autos...</div>;

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
                  {inquerito.numero.startsWith("TEMP-") ? inquerito.numero : `${inquerito.numero}/${inquerito.ano}`}
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
          
          <ScrollArea className="h-[500px] w-full pr-4">
            <div className="space-y-3">
              {documentos.length === 0 ? (
                <div className="py-12 text-center text-zinc-600 border border-zinc-800 border-dashed rounded-lg bg-zinc-900/40">
                  <FileType2 className="w-12 h-12 mx-auto mb-3 opacity-20" />
                  <p>Inquérito em branco.</p>
                  <p className="text-sm">Faça o upload do inquérito físico em PDF para a IA indexar.</p>
                </div>
              ) : (
                [...documentos]
                  .sort((a, b) => {
                    if (a.tipo_peca === "sintese_investigativa") return -1;
                    if (b.tipo_peca === "sintese_investigativa") return 1;
                    return 0;
                  })
                  .map((doc) => {
                    const isSintetico = doc.status_processamento === "sintetico";
                    return (
                      <div key={doc.id} className={`flex justify-between items-center p-4 rounded-lg border transition-colors ${isSintetico ? "bg-blue-500/5 border-blue-500/20 hover:border-blue-500/40" : "bg-zinc-900 border-zinc-800 hover:border-zinc-700"}`}>
                        <div className="flex items-center gap-4">
                          <div className={`p-2 rounded border ${isSintetico ? "bg-blue-500/10 text-blue-400 border-blue-500/20" : "bg-zinc-950 text-blue-400 border-zinc-800"}`}>
                            {isSintetico ? <Sparkles size={20}/> : <FileText size={20}/>}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-zinc-200 truncate max-w-sm">{doc.nome_arquivo}</p>
                            <p className="text-xs text-zinc-500 mt-0.5">
                              {isSintetico ? "Gerado automaticamente pela IA" : `Criado em ${new Date(doc.created_at).toLocaleDateString()}`}
                            </p>
                          </div>
                        </div>
                        <div>
                          {isSintetico ? (
                            <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 px-2 py-0.5 text-xs font-normal">
                              <Sparkles size={12} className="mr-1 inline"/> Análise AI
                            </Badge>
                          ) : doc.status_processamento === "concluido" ? (
                            <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20 px-2 py-0.5 text-xs font-normal">
                              <CheckCircle2 size={12} className="mr-1 inline"/> Indexado
                            </Badge>
                          ) : doc.status_processamento === "processando" ? (
                            <Badge variant="outline" className="bg-yellow-500/10 text-yellow-500 border-yellow-500/30 px-2 py-0.5 text-xs font-normal">
                              Lendo IA...
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="bg-zinc-800 text-zinc-400 border-zinc-700 px-2 py-0.5 text-xs font-normal">
                              {doc.status_processamento}
                            </Badge>
                          )}
                        </div>
                      </div>
                    );
                  })
              )}
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
                {intim.google_event_url && (
                  <a
                    href={intim.google_event_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors shrink-0"
                  >
                    <ExternalLink size={13} /> Google Agenda
                  </a>
                )}
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
    </div>
  );
}
