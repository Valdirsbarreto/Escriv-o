import { create } from "zustand";

interface PDFViewerState {
  open: boolean;
  url: string | null;
  page: number;
  titulo: string;
  docId: string | null;
}

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

  // PDF Viewer global (abre PDF na página da peça)
  pdfViewer: PDFViewerState;
  setPdfViewer: (state: Partial<PDFViewerState>) => void;
  closePdfViewer: () => void;

  // Comando do copiloto para abrir uma peça (ts garante unicidade do trigger)
  pecaParaAbrir: { pecaId: string; ts: number } | null;
  setPecaParaAbrir: (cmd: { pecaId: string; ts: number } | null) => void;

  // Painel de alertas do sistema
  isAlertasOpen: boolean;
  setAlertasOpen: (open: boolean) => void;
  toggleAlertas: () => void;
  alertasNaoLidos: number;
  setAlertasNaoLidos: (n: number) => void;
}

const PDF_VIEWER_INITIAL: PDFViewerState = { open: false, url: null, page: 1, titulo: '', docId: null };

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

  pdfViewer: PDF_VIEWER_INITIAL,
  setPdfViewer: (state) => set(prev => ({ pdfViewer: { ...prev.pdfViewer, open: true, ...state } })),
  closePdfViewer: () => set({ pdfViewer: PDF_VIEWER_INITIAL }),

  pecaParaAbrir: null,
  setPecaParaAbrir: (cmd) => set({ pecaParaAbrir: cmd }),

  isAlertasOpen: false,
  setAlertasOpen: (open) => set({ isAlertasOpen: open }),
  toggleAlertas: () => set((state) => ({ isAlertasOpen: !state.isAlertasOpen })),
  alertasNaoLidos: 0,
  setAlertasNaoLidos: (n) => set({ alertasNaoLidos: n }),
}));
