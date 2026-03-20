"use client";

import { useAppStore } from "@/store/app";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, Bot, User } from "lucide-react";
import { useState } from "react";
import { sendMessage, createSessao } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function CopilotoDrawer() {
  const { isCopilotoOpen, setCopilotoOpen, inqueritoAtivoId, sessaoChatId, setSessaoChatId } = useAppStore();
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>([
    { role: "bot", text: "Olá! Sou o Escrivão AI. Como posso ajudar com a investigação hoje?" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim() || !inqueritoAtivoId) return;
    
    const userText = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: userText }]);
    setLoading(true);

    try {
      let currentSessao = sessaoChatId;
      if (!currentSessao) {
        const novaSessao = await createSessao(inqueritoAtivoId);
        currentSessao = novaSessao.id;
        setSessaoChatId(currentSessao);
      }

      // TODO: Adaptar para usar stream real se necessário. 
      // O mock aqui só bate no endpoint normal.
      const resp = await sendMessage(currentSessao!, inqueritoAtivoId, userText);
      setMessages((prev) => [...prev, { role: "bot", text: resp.resposta }]);

    } catch (error) {
      console.error(error);
      setMessages((prev) => [...prev, { role: "bot", text: "Desculpe, ocorreu um erro ao se comunicar com o servidor." }]);
    } finally {
      setLoading(false);
    }
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
              {inqueritoAtivoId ? "Contexto ativo: Inquérito selecionado" : "Nenhum inquérito ativo selecionado."}
            </p>
          </div>
          <button onClick={() => setCopilotoOpen(false)} className="text-zinc-500 hover:text-zinc-300 transition-colors mt-0.5">
            ✕
          </button>
        </div>

        <ScrollArea className="flex-1 p-6">
          <div className="flex flex-col gap-4 pb-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === "user" ? "bg-blue-600" : "bg-zinc-800"}`}>
                  {msg.role === "user" ? <User size={16} /> : <Bot size={16} />}
                </div>
                <div className={`px-4 py-2 rounded-2xl max-w-[85%] text-sm overflow-hidden ${
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
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-zinc-800 bg-zinc-950">
          <form 
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="flex gap-2"
          >
            <Input 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Pergunte sobre o caso..."
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
