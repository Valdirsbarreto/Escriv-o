import { create } from "zustand";

interface AppState {
  inqueritoAtivoId: string | null;
  setInqueritoAtivoId: (id: string | null) => void;
  
  // Copiloto Global State
  isCopilotoOpen: boolean;
  setCopilotoOpen: (open: boolean) => void;
  toggleCopiloto: () => void;
  
  sessaoChatId: string | null;
  setSessaoChatId: (id: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  inqueritoAtivoId: null,
  setInqueritoAtivoId: (id) => set({ inqueritoAtivoId: id }),
  
  isCopilotoOpen: false,
  setCopilotoOpen: (open) => set({ isCopilotoOpen: open }),
  toggleCopiloto: () => set((state) => ({ isCopilotoOpen: !state.isCopilotoOpen })),
  
  sessaoChatId: null,
  setSessaoChatId: (id) => set({ sessaoChatId: id }),
}));
