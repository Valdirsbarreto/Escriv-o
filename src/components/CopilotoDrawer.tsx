"use client";

import { useAppStore } from "@/store/app";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, Bot, User, Save, Paperclip, X, FileText, Image, RefreshCw } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { agentChat, setAgentInquerito, clearAgentContext, createDocGerado, updateDocGerado, getDocsGerados } from "@/lib/api";

// ── Helpers ────────────────────────────────────────────────────────────────────

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = localStorage.getItem("escrivao_session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("escrivao_session_id", id);
  }
  return id;
}

function detectarTipo(text: string): string {
  const upper = text.toUpperCase();
  if (upper.includes("OITIVA") || upper.includes("ROTEIRO")) return "roteiro_oitiva";
  if (upper.includes("OFÍCIO") || upper.includes("OFICIO")) return "oficio";
  if (upper.includes("MANDADO") || upper.includes("REQUISIÇÃO") || upper.includes("REQUISICAO") || upper.includes("CAUTELAR")) return "minuta_cautelar";
  if (upper.includes("RELATÓRIO") || upper.includes("RELATORIO")) return "relatorio";
  return "outro";
}

function detectarTitulo(text: string): string {
  // Remove HTML tags para detectar o título
  const stripped = text.replace(/<[^>]+>/g, "").replace(/&[a-z]+;/gi, " ").trim();
  const lines = stripped.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.length > 0) return trimmed.slice(0, 80);
  }
  return stripped.slice(0, 80);
}

function detectarAbrirPeca(text: string): string | null {
  const match = text.match(/<ABRIR_PECA\s+peca_id="([^"]+)"\s*\/?>/i);
  return match ? match[1] : null;
}

function removerTagsXML(text: string): string {
  return text.replace(/<ABRIR_PECA\s+peca_id="[^"]+"\s*\/?>/gi, '').trim();
}

function pediriaDocumento(texto: string): boolean {
  const lower = texto.toLowerCase();
  const verbos = ["crie", "cria", "gere", "gera", "escreva", "escreve", "elabore", "elabora", "redija", "redigir", "faça", "faz", "monte"];
  const objetos = ["roteiro", "oitiva", "ofício", "oficio", "relatório", "relatorio", "documento", "minuta", "cautelar", "mandado", "requisição", "requisicao", "perguntas"];
  return verbos.some(v => lower.includes(v)) && objetos.some(o => lower.includes(o));
}

// Renderiza resposta do agente (HTML do Telegram) de forma segura
function AgentBotMessage({ html }: { html: string }) {
  return (
    <div
      className="text-sm text-zinc-300 leading-relaxed agent-response"
      dangerouslySetInnerHTML={{ __html: html.replace(/\n/g, "<br/>") }}
    />
  );
}

// ── Componente principal ───────────────────────────────────────────────────────

export function CopilotoDrawer() {
  const { isCopilotoOpen, setCopilotoOpen, inqueritoAtivoId, bumpDocsGerados, setPecaParaAbrir } = useAppStore();

  const [sessionId] = useState<string>(() => getOrCreateSessionId());
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>([
    { role: "bot", text: "Olá! Sou o <b>Escrivão AI</b>. Posso buscar nos autos, gerar cautelares, consultar OSINT, despachar inquéritos e muito mais.\n\nDiga <i>'ajuda'</i> para ver o que posso fazer." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [anexo, setAnexo] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [savedMsgs, setSavedMsgs] = useState<Set<number>>(new Set());
  const [savingMsg, setSavingMsg] = useState<number | null>(null);
  const [existingDocs, setExistingDocs] = useState<any[]>([]);
  const [confirmReplace, setConfirmReplace] = useState<{ index: number; text: string; titulo: string; tipo: string; existingDoc: any } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Sincroniza inquérito ativo no contexto Redis — limpa histórico ao trocar de IP
  const prevInqueritoId = useRef<string | null>(null);
  useEffect(() => {
    if (!inqueritoAtivoId || sessionId === "ssr") return;
    const trocou = prevInqueritoId.current && prevInqueritoId.current !== inqueritoAtivoId;
    prevInqueritoId.current = inqueritoAtivoId;
    setAgentInquerito(sessionId, inqueritoAtivoId).catch(() => {});
    if (trocou) {
      setMessages([{
        role: "bot",
        text: "🔄 <b>Inquérito alterado.</b> Contexto anterior encerrado.\nComo posso ajudar neste novo caso?"
      }]);
      setSavedMsgs(new Set());
    }
  }, [inqueritoAtivoId, sessionId]);

  // Busca docs existentes para oferecer substituição
  useEffect(() => {
    if (inqueritoAtivoId) {
      getDocsGerados(inqueritoAtivoId).then(r => setExistingDocs(r.data || [])).catch(() => {});
    }
  }, [inqueritoAtivoId]);

  // Auto-scroll para a última mensagem
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Escuta CustomEvent "copiloto:prefill" disparado pela aba Blockchain
  useEffect(() => {
    const handler = (e: Event) => {
      const texto = (e as CustomEvent<string>).detail;
      if (texto) {
        setInput(texto);
        setCopilotoOpen(true);
      }
    };
    window.addEventListener("copiloto:prefill", handler);
    return () => window.removeEventListener("copiloto:prefill", handler);
  }, [setCopilotoOpen]);

  const handleSend = async () => {
    if (!input.trim() && !anexo) return;

    const userText = input.trim() || (anexo ? `Analise o arquivo: ${anexo.name}` : "");
    setInput("");
    setAnexo(null);
    if (fileInputRef.current) fileInputRef.current.value = "";

    // Garante que o contexto do inquérito está sincronizado antes de enviar
    if (inqueritoAtivoId && sessionId !== "ssr") {
      await setAgentInquerito(sessionId, inqueritoAtivoId).catch(() => {});
    }

    const userLabel = anexo ? `📎 ${anexo.name}\n${userText}` : userText;
    setMessages(prev => [...prev, { role: "user", text: userLabel }]);
    setLoading(true);

    try {
      const data = await agentChat(userText, sessionId, inqueritoAtivoId);
      const botText = data.resposta;
      const newIndex = messages.length + 1;

      // Detecta e executa comando <ABRIR_PECA peca_id="uuid"/>
      const pecaId = detectarAbrirPeca(botText);
      if (pecaId) setPecaParaAbrir({ pecaId, ts: Date.now() });

      setMessages(prev => [...prev, { role: "bot", text: removerTagsXML(botText) }]);

      // Auto-salva se o usuário pediu para criar um documento
      if (inqueritoAtivoId && pediriaDocumento(userText) && botText.length > 300) {
        try {
          const titulo = detectarTitulo(botText);
          const tipo = detectarTipo(botText);
          await createDocGerado(inqueritoAtivoId, { titulo, tipo, conteudo: botText });
          setSavedMsgs(prev => new Set(prev).add(newIndex));
          bumpDocsGerados();
        } catch {}
      }
    } catch {
      setMessages(prev => [...prev, { role: "bot", text: "⚠️ Erro ao se comunicar com o servidor. Tente novamente." }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSalvar = async (index: number, text: string) => {
    if (!inqueritoAtivoId) return;
    const titulo = detectarTitulo(text);
    const tipo = detectarTipo(text);
    const docExistente = existingDocs.find(d => d.tipo === tipo);
    if (docExistente) {
      setConfirmReplace({ index, text, titulo, tipo, existingDoc: docExistente });
      return;
    }
    await _executarSave(index, text, titulo, tipo, null);
  };

  const _executarSave = async (index: number, text: string, titulo: string, tipo: string, substituirId: string | null) => {
    if (!inqueritoAtivoId) return;
    setSavingMsg(index);
    try {
      if (substituirId) {
        await updateDocGerado(inqueritoAtivoId, substituirId, { titulo, tipo, conteudo: text });
        setExistingDocs(prev => prev.map(d => d.id === substituirId ? { ...d, titulo, tipo } : d));
      } else {
        await createDocGerado(inqueritoAtivoId, { titulo, tipo, conteudo: text });
        getDocsGerados(inqueritoAtivoId).then(r => setExistingDocs(r.data || [])).catch(() => {});
      }
      setSavedMsgs(prev => new Set(prev).add(index));
      bumpDocsGerados();
    } catch {
      alert("Erro ao salvar documento no inquérito.");
    } finally {
      setSavingMsg(null);
    }
  };

  const handleNovaConversa = async () => {
    await clearAgentContext(sessionId).catch(() => {});
    setMessages([{ role: "bot", text: "Conversa reiniciada. Como posso ajudar?" }]);
    setSavedMsgs(new Set());
  };

  if (!isCopilotoOpen) return null;

  return (
    <>
      {/* Estilos para o HTML do agente */}
      <style>{`
        .agent-response b { color: #e4e4e7; font-weight: 600; }
        .agent-response i { color: #a1a1aa; font-style: italic; }
        .agent-response code { background: #18181b; border: 1px solid #3f3f46; padding: 1px 6px; border-radius: 4px; font-family: monospace; font-size: 0.8em; color: #d4d4d8; }
        .agent-response a { color: #60a5fa; text-decoration: underline; text-underline-offset: 2px; }
        .agent-response pre { background: #18181b; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px 12px; overflow-x: auto; margin: 6px 0; }
      `}</style>

      <aside
        className="w-[420px] shrink-0 bg-zinc-950 border-l border-zinc-800 flex flex-col max-h-screen sticky top-0"
        onWheel={(e) => e.stopPropagation()}
      >
        <div className="p-6 border-b border-zinc-800 flex items-start justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-zinc-100 font-semibold">
              <Bot className="text-blue-500" />
              Agente Investigativo
            </h2>
            <p className="text-sm text-zinc-500 mt-1">
              {inqueritoAtivoId ? "Inquérito em foco • Function Calling ativo" : "Nenhum inquérito ativo."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleNovaConversa}
              title="Nova conversa"
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <RefreshCw size={15} />
            </button>
            <button onClick={() => setCopilotoOpen(false)} className="text-zinc-500 hover:text-zinc-300 transition-colors">
              ✕
            </button>
          </div>
        </div>

        <ScrollArea className="flex-1 p-6 overscroll-contain">
          <div className="flex flex-col gap-4 pb-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === "user" ? "bg-blue-600" : "bg-zinc-800"}`}>
                  {msg.role === "user" ? <User size={16} /> : <Bot size={16} />}
                </div>
                <div className="flex flex-col gap-1 max-w-[85%]">
                  <div className={`px-4 py-2 rounded-2xl text-sm overflow-hidden ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white rounded-tr-none"
                      : "bg-zinc-900 border border-zinc-800 rounded-tl-none"
                  }`}>
                    {msg.role === "user" ? (
                      <span className="whitespace-pre-wrap">{msg.text}</span>
                    ) : (
                      <AgentBotMessage html={msg.text} />
                    )}
                  </div>
                  {msg.role === "bot" && i > 0 && (
                    <div className="pl-1">
                      {savedMsgs.has(i) ? (
                        <span className="text-xs text-green-400">Salvo no inquérito</span>
                      ) : (
                        <button
                          onClick={() => handleSalvar(i, msg.text)}
                          disabled={savingMsg === i || !inqueritoAtivoId}
                          className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40"
                        >
                          <Save size={11} />
                          {savingMsg === i ? "Salvando..." : "Salvar na área do inquérito"}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center shrink-0">
                  <Bot size={16} />
                </div>
                <div className="px-4 py-2 rounded-2xl bg-zinc-900 border border-zinc-800 text-zinc-500 text-sm rounded-tl-none">
                  Processando...
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-zinc-800 bg-zinc-950 space-y-2">
          {anexo && (
            <div className="flex items-center gap-2 bg-zinc-800/70 border border-zinc-700 rounded-lg px-3 py-2">
              {anexo.type.startsWith("image/") ? (
                <Image size={14} className="text-blue-400 shrink-0" />
              ) : (
                <FileText size={14} className="text-amber-400 shrink-0" />
              )}
              <span className="text-xs text-zinc-300 truncate flex-1">{anexo.name}</span>
              <span className="text-xs text-zinc-500 shrink-0">{(anexo.size / 1024).toFixed(0)} KB</span>
              <button
                onClick={() => { setAnexo(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                className="text-zinc-500 hover:text-zinc-300 transition-colors ml-1 shrink-0"
              >
                <X size={13} />
              </button>
            </div>
          )}

          <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.tiff,.webp"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) setAnexo(f); }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={loading}
              title="Anexar arquivo"
              className={`shrink-0 p-2 rounded-md border transition-colors disabled:opacity-40 ${
                anexo
                  ? "border-amber-500/40 text-amber-400 bg-amber-500/10"
                  : "border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600"
              }`}
            >
              <Paperclip size={16} />
            </button>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={anexo ? "Instrução para o arquivo (opcional)..." : "Pergunte, ordene ou solicite..."}
              className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
              disabled={loading}
            />
            <Button
              type="submit"
              size="icon"
              disabled={loading || (!input.trim() && !anexo)}
              className="bg-blue-600 hover:bg-blue-700"
            >
              <Send size={18} />
            </Button>
          </form>
        </div>

        {/* Diálogo de confirmação de substituição */}
        {confirmReplace && (
          <div className="absolute inset-0 z-10 flex items-end justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 mx-4 mb-6 w-full shadow-xl">
              <p className="text-sm font-semibold text-zinc-100 mb-1">Substituir documento existente?</p>
              <p className="text-xs text-zinc-400 mb-4">
                Já existe um <span className="text-zinc-200">{confirmReplace.existingDoc.titulo}</span> salvo. Quer substituí-lo ou criar um novo?
              </p>
              <div className="flex gap-2">
                <button
                  onClick={async () => { const cr = confirmReplace; setConfirmReplace(null); await _executarSave(cr.index, cr.text, cr.titulo, cr.tipo, cr.existingDoc.id); }}
                  className="flex-1 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded-lg px-3 py-2 transition-colors"
                >
                  Substituir
                </button>
                <button
                  onClick={async () => { const cr = confirmReplace; setConfirmReplace(null); await _executarSave(cr.index, cr.text, cr.titulo, cr.tipo, null); }}
                  className="flex-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded-lg px-3 py-2 transition-colors"
                >
                  Criar novo
                </button>
                <button
                  onClick={() => setConfirmReplace(null)}
                  className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-2 transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
