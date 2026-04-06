"use client";

import { useAppStore } from "@/store/app";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, Bot, User, Save } from "lucide-react";
import { useState } from "react";
import { sendMessage, createSessao, createDocGerado } from "@/lib/api";
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
  const verbos = ["crie", "cria", "gere", "gera", "escreva", "escreve", "elabore", "elabora", "redija", "redigir", "faça", "faz", "monte", "salve", "salva"];
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
  const { isCopilotoOpen, setCopilotoOpen, inqueritoAtivoId, sessaoChatId, setSessaoChatId } = useAppStore();
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>([
    { role: "bot", text: "Olá! Sou o Escrivão AI. Como posso ajudar com a investigação hoje?" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [savedMsgs, setSavedMsgs] = useState<Set<number>>(new Set());
  const [savingMsg, setSavingMsg] = useState<number | null>(null);

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

      const resp = await sendMessage(currentSessao!, inqueritoAtivoId, userText);
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
    setSavingMsg(index);
    try {
      const titulo = detectarTitulo(text);
      const tipo = detectarTipo(text);
      await createDocGerado(inqueritoAtivoId, { titulo, tipo, conteudo: text });
      setSavedMsgs((prev) => new Set(prev).add(index));
    } catch (error) {
      console.error("Erro ao salvar documento:", error);
      alert("Erro ao salvar documento no inquérito.");
    } finally {
      setSavingMsg(null);
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
