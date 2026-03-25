"use client";

import { useAppStore } from "@/store/app";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, Bot, User, FileText, CheckCircle, Copy } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { sendMessage, createSessao } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Msg = {
  role: "user" | "bot";
  text: string;
  modo?: string;
  tipoDocumento?: string;
};

export function CopilotoDrawer() {
  const { isCopilotoOpen, setCopilotoOpen, inqueritoAtivoId, sessaoChatId, setSessaoChatId } = useAppStore();
  const [messages, setMessages] = useState<Msg[]>([
    { role: "bot", text: "Olá! Sou o Escrivão AI. Como posso ajudar com a investigação hoje?" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [modoEdicao, setModoEdicao] = useState(false);
  const [tipoDocAtivo, setTipoDocAtivo] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async (textoOverride?: string) => {
    const texto = textoOverride ?? input;
    if (!texto.trim() || !inqueritoAtivoId) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: texto }]);
    setLoading(true);

    try {
      let currentSessao = sessaoChatId;
      if (!currentSessao) {
        const novaSessao = await createSessao(inqueritoAtivoId);
        currentSessao = novaSessao.id;
        setSessaoChatId(currentSessao);
      }

      const resp = await sendMessage(currentSessao!, inqueritoAtivoId, texto);
      const modo = resp.modo ?? "";

      if (modo === "edicao_documento") {
        setModoEdicao(true);
        setTipoDocAtivo(resp.tipo_documento ?? "");
      } else if (modo === "documento_aprovado") {
        setModoEdicao(false);
        setTipoDocAtivo("");
      }

      setMessages((prev) => [...prev, {
        role: "bot",
        text: resp.resposta,
        modo,
        tipoDocumento: resp.tipo_documento,
      }]);
    } catch (error) {
      console.error(error);
      setMessages((prev) => [...prev, { role: "bot", text: "Desculpe, ocorreu um erro ao se comunicar com o servidor." }]);
    } finally {
      setLoading(false);
    }
  };

  const handleAprovar = () => handleSend("aprovado");

  const handleCopiar = (texto: string) => {
    navigator.clipboard.writeText(texto).catch(() => {});
  };

  if (!isCopilotoOpen) return null;

  return (
    <aside className="w-[420px] shrink-0 bg-zinc-950 border-l border-zinc-800 flex flex-col max-h-screen sticky top-0">
      <div className="p-6 border-b border-zinc-800 flex items-start justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-zinc-100 font-semibold">
            <Bot className="text-blue-500" />
            Copiloto Investigativo
          </h2>
          <p className="text-sm text-zinc-500 mt-1">
            {modoEdicao
              ? `✏️ Editando: ${tipoDocAtivo.replace(/_/g, " ")}`
              : inqueritoAtivoId
                ? "Contexto ativo: Inquérito selecionado"
                : "Nenhum inquérito ativo selecionado."}
          </p>
        </div>
        <button onClick={() => setCopilotoOpen(false)} className="text-zinc-500 hover:text-zinc-300 transition-colors mt-0.5">
          ✕
        </button>
      </div>

      <ScrollArea className="flex-1 p-6">
        <div className="flex flex-col gap-4 pb-4">
          {messages.map((msg, i) => {
            const isDoc = msg.modo === "edicao_documento";
            return (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === "user" ? "bg-blue-600" : isDoc ? "bg-amber-900" : "bg-zinc-800"
                }`}>
                  {msg.role === "user" ? <User size={16} /> : isDoc ? <FileText size={16} className="text-amber-300" /> : <Bot size={16} />}
                </div>
                <div className={`rounded-2xl max-w-[85%] text-sm overflow-hidden ${
                  msg.role === "user"
                    ? "px-4 py-2 bg-blue-600 text-white rounded-tr-none"
                    : isDoc
                      ? "w-full border border-amber-700/40 bg-amber-950/20 rounded-tl-none"
                      : "px-4 py-2 bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-tl-none"
                }`}>
                  {msg.role === "user" ? (
                    msg.text
                  ) : isDoc ? (
                    <div>
                      <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-amber-700/30">
                        <span className="text-[11px] font-semibold text-amber-400 uppercase tracking-wide flex items-center gap-1.5">
                          <FileText size={12} /> Rascunho
                        </span>
                        <button
                          onClick={() => handleCopiar(msg.text)}
                          className="text-zinc-500 hover:text-zinc-300 transition-colors"
                          title="Copiar documento"
                        >
                          <Copy size={13} />
                        </button>
                      </div>
                      <div className="px-4 py-3 text-zinc-300">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                          {msg.text}
                        </ReactMarkdown>
                      </div>
                    </div>
                  ) : (
                    <div className="px-0 py-0">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                        {msg.text}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {loading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center shrink-0">
                <Bot size={16} />
              </div>
              <div className="px-4 py-2 rounded-2xl bg-zinc-900 border border-zinc-800 text-zinc-500 text-sm rounded-tl-none">
                {modoEdicao ? "Atualizando rascunho..." : "Digitando..."}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="p-4 border-t border-zinc-800 bg-zinc-950 space-y-2">
        {modoEdicao && (
          <Button
            onClick={handleAprovar}
            disabled={loading}
            className="w-full bg-green-700 hover:bg-green-600 text-white flex items-center gap-2"
          >
            <CheckCircle size={16} />
            Aprovar e salvar documento
          </Button>
        )}
        <form
          onSubmit={(e) => { e.preventDefault(); handleSend(); }}
          className="flex gap-2"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={modoEdicao ? "Solicite ajustes no documento..." : "Pergunte ou solicite um documento..."}
            className="bg-zinc-900 border-zinc-800 focus-visible:ring-blue-500"
            disabled={loading || !inqueritoAtivoId}
          />
          <Button type="submit" size="icon" disabled={loading || !inqueritoAtivoId || !input.trim()} className="bg-blue-600 hover:bg-blue-700">
            <Send size={18} />
          </Button>
        </form>
      </div>
    </aside>
  );
}

const mdComponents = {
  p: ({ node, ...props }: any) => <p className="mb-3 last:mb-0 leading-relaxed" {...props} />,
  a: ({ node, ...props }: any) => <a target="_blank" className="text-blue-400 hover:text-blue-300 underline underline-offset-2 font-medium" {...props} />,
  ul: ({ node, ...props }: any) => <ul className="list-disc pl-5 mb-3 space-y-1" {...props} />,
  ol: ({ node, ...props }: any) => <ol className="list-decimal pl-5 mb-3 space-y-1" {...props} />,
  li: ({ node, ...props }: any) => <li className="pl-1" {...props} />,
  strong: ({ node, ...props }: any) => <strong className="font-semibold text-zinc-100" {...props} />,
  blockquote: ({ node, ...props }: any) => <blockquote className="border-l-2 border-zinc-600 pl-3 italic text-zinc-400 mb-3" {...props} />,
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
          <code className={className} {...props}>{children}</code>
        </pre>
      </div>
    );
  },
};
