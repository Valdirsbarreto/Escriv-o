"use client";

import { useAppStore } from "@/store/app";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, Bot, User, Save, Paperclip, X, FileText, Image } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { sendMessage, sendMessageComAnexo, createSessao, createDocGerado, updateDocGerado, getDocsGerados } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function detectarTipo(text: string): string {
  const upper = text.toUpperCase();
  if (upper.includes("OITIVA") || upper.includes("ROTEIRO")) return "roteiro_oitiva";
  if (upper.includes("OFÍCIO") || upper.includes("OFICIO")) return "oficio";
  if (upper.includes("MANDADO") || upper.includes("REQUISIÇÃO") || upper.includes("REQUISICAO") || upper.includes("CAUTELAR")) return "minuta_cautelar";
  if (upper.includes("RELATÓRIO") || upper.includes("RELATORIO")) return "relatorio";
  return "outro";
}

function pediriaDocumento(texto: string): boolean {
  const lower = texto.toLowerCase();
  // Apenas verbos de CRIAÇÃO — "salve/salva" removidos pois aparecem no texto do botão UI
  const verbos = ["crie", "cria", "gere", "gera", "escreva", "escreve", "elabore", "elabora", "redija", "redigir", "faça", "faz", "monte"];
  const objetos = ["roteiro", "oitiva", "ofício", "oficio", "relatório", "relatorio", "documento", "minuta", "cautelar", "mandado", "requisição", "requisicao", "perguntas"];
  return verbos.some(v => lower.includes(v)) && objetos.some(o => lower.includes(o));
}

function detectarTitulo(text: string): string {
  const lines = text.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("#")) {
      return trimmed.replace(/^#+\s*/, "").slice(0, 500);
    }
    if (trimmed.length > 0) {
      return trimmed.slice(0, 80);
    }
  }
  return text.slice(0, 80);
}

export function CopilotoDrawer() {
  const { isCopilotoOpen, setCopilotoOpen, inqueritoAtivoId, sessaoChatId, setSessaoChatId, bumpDocsGerados } = useAppStore();
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>([
    { role: "bot", text: "Olá! Sou o Escrivão AI. Como posso ajudar com a investigação hoje?" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [anexo, setAnexo] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [savedMsgs, setSavedMsgs] = useState<Set<number>>(new Set());
  const [savingMsg, setSavingMsg] = useState<number | null>(null);
  const [existingDocs, setExistingDocs] = useState<any[]>([]);
  // confirmReplace: { index, text, titulo, tipo, existingDoc } — aguarda confirmação do usuário
  const [confirmReplace, setConfirmReplace] = useState<{ index: number; text: string; titulo: string; tipo: string; existingDoc: any } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

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

  const handleSend = async () => {
    if ((!input.trim() && !anexo) || !inqueritoAtivoId) return;

    const userText = input.trim() || (anexo ? `Analise o arquivo: ${anexo.name}` : "");
    const arquivoAnexado = anexo;
    setInput("");
    setAnexo(null);
    if (fileInputRef.current) fileInputRef.current.value = "";

    const userLabel = arquivoAnexado
      ? `📎 ${arquivoAnexado.name}\n${userText}`
      : userText;
    setMessages((prev) => [...prev, { role: "user", text: userLabel }]);
    setLoading(true);

    try {
      let currentSessao = sessaoChatId;
      if (!currentSessao) {
        const novaSessao = await createSessao(inqueritoAtivoId);
        currentSessao = novaSessao.id;
        setSessaoChatId(currentSessao);
      }

      const resp = arquivoAnexado
        ? await sendMessageComAnexo(currentSessao!, userText, arquivoAnexado)
        : await sendMessage(currentSessao!, inqueritoAtivoId, userText);

      const botText = resp.resposta;
      const newIndex = messages.length + 1; // +1 para contar a mensagem do user que acabou de entrar

      setMessages((prev) => [...prev, { role: "bot", text: botText }]);

      // Auto-salva se o usuário pediu para criar um documento e a resposta é substancial
      if (pediriaDocumento(userText) && botText.length > 300) {
        try {
          const titulo = detectarTitulo(botText);
          const tipo = detectarTipo(botText);
          await createDocGerado(inqueritoAtivoId, { titulo, tipo, conteudo: botText });
          setSavedMsgs((prev) => new Set(prev).add(newIndex));
          bumpDocsGerados();
        } catch (saveErr) {
          console.error("Erro ao auto-salvar documento:", saveErr);
        }
      }

    } catch (error) {
      console.error(error);
      setMessages((prev) => [...prev, { role: "bot", text: "Desculpe, ocorreu um erro ao se comunicar com o servidor." }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSalvar = async (index: number, text: string) => {
    if (!inqueritoAtivoId) return;
    const titulo = detectarTitulo(text);
    const tipo = detectarTipo(text);
    // Verifica se já existe doc do mesmo tipo — oferece substituição
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
      setSavedMsgs((prev) => new Set(prev).add(index));
      bumpDocsGerados();
    } catch (error) {
      console.error("Erro ao salvar documento:", error);
      alert("Erro ao salvar documento no inquérito.");
    } finally {
      setSavingMsg(null);
    }
  };

  if (!isCopilotoOpen) return null;

  return (
    <aside
      className="w-[420px] shrink-0 bg-zinc-950 border-l border-zinc-800 flex flex-col max-h-screen sticky top-0"
      onWheel={(e) => e.stopPropagation()}
    >
        <div className="p-6 border-b border-zinc-800 flex items-start justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-zinc-100 font-semibold">
              <Bot className="text-blue-500" />
              Copiloto Investigativo
            </h2>
            <p className="text-sm text-zinc-500 mt-1">
              {inqueritoAtivoId ? "Contexto ativo: Inquérito selecionado" : "Nenhum inquérito ativo selecionado."}
            </p>
          </div>
          <button onClick={() => setCopilotoOpen(false)} className="text-zinc-500 hover:text-zinc-300 transition-colors mt-0.5">
            ✕
          </button>
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
                      : "bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-tl-none"
                  }`}>
                    {msg.role === "user" ? (
                      msg.text
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ node, ...props }) => <p className="mb-3 last:mb-0 leading-relaxed" {...props} />,
                          a: ({ node, ...props }) => <a target="_blank" className="text-blue-400 hover:text-blue-300 underline underline-offset-2 font-medium" {...props} />,
                          ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-3 space-y-1" {...props} />,
                          ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-3 space-y-1" {...props} />,
                          li: ({ node, ...props }) => <li className="pl-1" {...props} />,
                          strong: ({ node, ...props }) => <strong className="font-semibold text-zinc-100" {...props} />,
                          blockquote: ({ node, ...props }) => <blockquote className="border-l-2 border-zinc-600 pl-3 italic text-zinc-400 mb-3" {...props} />,
                          code: ({ node, className, children, ...props }: any) => {
                            const match = /language-(\w+)/.exec(className || "");
                            const inline = !match && !className?.includes("language-");
                            return inline ? (
                              <code className="bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-200 text-xs font-mono" {...props}>
                                {children}
                              </code>
                            ) : (
                              <div className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden mb-3">
                                <div className="bg-zinc-900 px-3 py-1 text-[10px] text-zinc-500 font-mono uppercase border-b border-zinc-800">{match?.[1] || "code"}</div>
                                <pre className="p-3 overflow-x-auto text-xs font-mono text-zinc-200">
                                  <code className={className} {...props}>
                                    {children}
                                  </code>
                                </pre>
                              </div>
                            );
                          },
                        }}
                      >
                        {msg.text}
                      </ReactMarkdown>
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
                  Digitando...
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-zinc-800 bg-zinc-950 space-y-2">
          {/* Preview do anexo */}
          {anexo && (
            <div className="flex items-center gap-2 bg-zinc-800/70 border border-zinc-700 rounded-lg px-3 py-2">
              {anexo.type.startsWith("image/") ? (
                <Image size={14} className="text-blue-400 shrink-0" />
              ) : (
                <FileText size={14} className="text-amber-400 shrink-0" />
              )}
              <span className="text-xs text-zinc-300 truncate flex-1">{anexo.name}</span>
              <span className="text-xs text-zinc-500 shrink-0">
                {(anexo.size / 1024).toFixed(0)} KB
              </span>
              <button
                onClick={() => { setAnexo(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                className="text-zinc-500 hover:text-zinc-300 transition-colors ml-1 shrink-0"
              >
                <X size={13} />
              </button>
            </div>
          )}

          <form
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="flex gap-2"
          >
            {/* Input oculto para arquivo */}
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.tiff,.webp"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) setAnexo(f);
              }}
            />
            {/* Botão clipe */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={loading || !inqueritoAtivoId}
              title="Anexar arquivo (PDF, imagem ou texto)"
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
              placeholder={anexo ? "Instrução para o arquivo (opcional)..." : "Pergunte sobre o caso..."}
              className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
              disabled={loading || !inqueritoAtivoId}
            />
            <Button
              type="submit"
              size="icon"
              disabled={loading || !inqueritoAtivoId || (!input.trim() && !anexo)}
              className="bg-blue-600 hover:bg-blue-700"
            >
              <Send size={18} />
            </Button>
          </form>
        </div>

        {/* Diálogo de confirmação de substituição */}
        {confirmReplace && (
          <div className="absolute inset-0 z-10 flex items-end justify-center bg-black/60 backdrop-blur-sm rounded-none">
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
  );
}
