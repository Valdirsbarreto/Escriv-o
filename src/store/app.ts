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

  // Sinaliza para page.tsx re-buscar docs gerados após save do copiloto
  docsGeradosVersion: number;
  bumpDocsGerados: () => void;

  // Controle de colapso da sidebar (recolhe ao abrir um inquérito)
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  inqueritoAtivoId: null,
  setInqueritoAtivoId: (id) => set({ inqueritoAtivoId: id }),

  isCopilotoOpen: false,
  setCopilotoOpen: (open) => set({ isCopilotoOpen: open }),
  toggleCopiloto: () => set((state) => ({ isCopilotoOpen: !state.isCopilotoOpen })),

  sessaoChatId: null,
  setSessaoChatId: (id) => set({ sessaoChatId: id }),

  docsGeradosVersion: 0,
  bumpDocsGerados: () => set((state) => ({ docsGeradosVersion: state.docsGeradosVersion + 1 })),

  sidebarCollapsed: false,
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
}));
