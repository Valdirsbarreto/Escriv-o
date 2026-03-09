"use client";

import { useAppStore } from "@/store/app";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, Bot, User } from "lucide-react";
import { useState } from "react";
import { sendMessage, createSessao } from "@/lib/api";

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

  return (
    <Sheet open={isCopilotoOpen} onOpenChange={setCopilotoOpen}>
      <SheetContent className="w-[400px] sm:w-[540px] bg-zinc-950 border-zinc-800 flex flex-col p-0">
        <SheetHeader className="p-6 border-b border-zinc-800">
          <SheetTitle className="flex items-center gap-2 text-zinc-100">
            <Bot className="text-blue-500" />
            Copiloto Investigativo
          </SheetTitle>
          <SheetDescription className="text-zinc-500">
            {inqueritoAtivoId ? "Contexto ativo: Inquérito selecionado" : "Nenhum inquérito ativo selecionado. Escolha um na dashboard."}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 p-6">
          <div className="flex flex-col gap-4 pb-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === "user" ? "bg-blue-600" : "bg-zinc-800"}`}>
                  {msg.role === "user" ? <User size={16} /> : <Bot size={16} />}
                </div>
                <div className={`px-4 py-2 rounded-2xl max-w-[80%] text-sm ${
                  msg.role === "user" 
                    ? "bg-blue-600 text-white rounded-tr-none" 
                    : "bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-tl-none"
                }`}>
                  {msg.text}
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
      </SheetContent>
    </Sheet>
  );
}
