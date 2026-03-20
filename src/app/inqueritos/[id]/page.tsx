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
  DialogClose,
} from "@/components/ui/dialog";
import { FolderOpen, ArrowLeft, Upload, FileText, CheckCircle2, FileType2, Trash2 } from "lucide-react";

export default function InqueritoDetalhePage() {
  const params = useParams();
  const router = useRouter();
  const inqId = params.id as string;
  const { setInqueritoAtivoId, setCopilotoOpen } = useAppStore();

  const [inquerito, setInq] = useState<any>(null);
  const [documentos, setDocumentos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDados = async () => {
    try {
      const [inqRes, docsRes] = await Promise.all([
        api.get(`/inqueritos/${inqId}`),
        api.get(`/inqueritos/${inqId}/documentos`)
      ]);
      setInq(inqRes.data);
      setDocumentos(docsRes.data);
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
    return () => setCopilotoOpen(false);
  }, [inqId]);

  const handleDelete = async () => {
    try {
      await deleteInquerito(inqId);
      router.push("/inqueritos");
    } catch (e) {
      console.error(e);
      alert("Erro ao excluir inquérito.");
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
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
              {inquerito.numero}/{inquerito.ano}
            </h1>
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
          <Dialog>
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
                <DialogClose render={<Button variant="outline" className="bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700" />}>
                  Cancelar
                </DialogClose>
                <Button onClick={handleDelete} className="bg-red-700 hover:bg-red-600 text-white">
                  Excluir permanentemente
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="bg-blue-600 hover:bg-blue-700 text-white">
            {uploading ? (
              <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin mr-2" />
            ) : (
              <Upload size={18} className="mr-2"/>
            )}
            {uploading ? "Enviando..." : "Anexar Petição/PDF"}
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
            <span className="text-sm text-zinc-500">{documentos.length} peças anexadas</span>
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
                documentos.map((doc) => (
                  <div key={doc.id} className="flex justify-between items-center bg-zinc-900 border border-zinc-800 p-4 rounded-lg hover:border-zinc-700 transition-colors">
                    <div className="flex items-center gap-4">
                      <div className="bg-zinc-950 p-2 rounded text-blue-400 border border-zinc-800">
                        <FileText size={20}/>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-zinc-200 truncate max-w-sm">{doc.nome_arquivo}</p>
                        <p className="text-xs text-zinc-500 mt-0.5">Criado em {new Date(doc.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                    <div>
                      {doc.status_processamento === "concluido" ? (
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
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
