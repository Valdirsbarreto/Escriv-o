'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { ChevronLeft, ChevronRight, ExternalLink, X, Loader2, FileText, ZoomIn, ZoomOut } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';

interface PDFViewerProps {
  url: string;
  initialPage: number;
  titulo?: string;
  onClose: () => void;
}

export default function PDFViewer({ url, initialPage, titulo, onClose }: PDFViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<any>(null);
  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [pageInput, setPageInput] = useState('1');
  const [zoom, setZoom] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Configura worker via CDN (deve rodar só no browser)
  useEffect(() => {
    pdfjsLib.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;
  }, []);

  // Carrega o documento PDF
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    setPdfDoc(null);

    pdfjsLib.getDocument({ url, withCredentials: false }).promise
      .then(doc => {
        if (cancelled) return;
        setPdfDoc(doc);
        setTotalPages(doc.numPages);
        const safePage = Math.min(Math.max(1, initialPage), doc.numPages);
        setCurrentPage(safePage);
        setPageInput(String(safePage));
      })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [url, initialPage]);

  // Renderiza a página atual no canvas
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;

    if (renderTaskRef.current) {
      renderTaskRef.current.cancel();
      renderTaskRef.current = null;
    }

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d')!;

    pdfDoc.getPage(currentPage).then((page: any) => {
      const containerWidth = canvas.parentElement?.clientWidth ?? 800;
      const naturalVp = page.getViewport({ scale: 1 });
      const scale = ((containerWidth * 0.95) / naturalVp.width) * zoom;
      const viewport = page.getViewport({ scale });

      canvas.width = viewport.width;
      canvas.height = viewport.height;

      const task = page.render({ canvasContext: ctx, viewport });
      renderTaskRef.current = task;

      task.promise
        .then(() => { renderTaskRef.current = null; })
        .catch((err: any) => {
          if (err?.name !== 'RenderingCancelledException') console.error(err);
        });
    });
  }, [pdfDoc, currentPage, zoom]);

  const goTo = useCallback((page: number) => {
    const p = Math.min(Math.max(1, page), totalPages);
    setCurrentPage(p);
    setPageInput(String(p));
  }, [totalPages]);

  // Fecha com Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') goTo(currentPage + 1);
      if (e.key === 'ArrowLeft') goTo(currentPage - 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, currentPage, goTo]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/85 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl mx-4"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <FileText size={16} className="text-amber-400 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-zinc-100 truncate">{titulo || 'Documento'}</p>
              {totalPages > 0 && (
                <p className="text-xs text-zinc-500">Página {currentPage} de {totalPages}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-4">
            <button
              onClick={() => setZoom(z => Math.max(0.5, z - 0.2))}
              title="Reduzir zoom"
              className="p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <ZoomOut size={15} />
            </button>
            <span className="text-xs text-zinc-600 w-10 text-center">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom(z => Math.min(3, z + 0.2))}
              title="Aumentar zoom"
              className="p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <ZoomIn size={15} />
            </button>
            <div className="w-px h-4 bg-zinc-700 mx-1" />
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 rounded-lg px-2.5 py-1.5 transition-colors"
            >
              <ExternalLink size={11} /> Nova aba
            </a>
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors ml-1"
            >
              <X size={17} />
            </button>
          </div>
        </div>

        {/* Canvas */}
        <div className="flex-1 overflow-auto flex items-start justify-center p-4 bg-zinc-950/50 min-h-0">
          {loading && (
            <div className="flex items-center gap-3 text-zinc-500 py-20">
              <Loader2 size={22} className="animate-spin text-blue-400" />
              <span className="text-sm">Carregando PDF...</span>
            </div>
          )}
          {error && (
            <div className="text-center py-20 text-zinc-500">
              <FileText size={40} className="mx-auto mb-3 opacity-20" />
              <p className="text-sm mb-3">Não foi possível carregar o PDF.</p>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-400 hover:text-blue-300 underline"
              >
                Abrir em nova aba
              </a>
            </div>
          )}
          {!loading && !error && (
            <canvas ref={canvasRef} className="max-w-full shadow-xl rounded" />
          )}
        </div>

        {/* Navegação */}
        {totalPages > 0 && (
          <div className="px-5 py-3 border-t border-zinc-800 flex items-center justify-between shrink-0">
            <button
              onClick={() => goTo(currentPage - 1)}
              disabled={currentPage <= 1}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1.5 rounded border border-zinc-700 hover:border-zinc-600 transition-colors"
            >
              <ChevronLeft size={14} /> Anterior
            </button>
            <div className="flex items-center gap-2 text-sm">
              <input
                type="number"
                value={pageInput}
                onChange={e => setPageInput(e.target.value)}
                onBlur={() => goTo(Number(pageInput))}
                onKeyDown={e => e.key === 'Enter' && goTo(Number(pageInput))}
                min={1}
                max={totalPages}
                className="w-14 text-center bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-blue-500"
              />
              <span className="text-xs text-zinc-500">/ {totalPages}</span>
            </div>
            <button
              onClick={() => goTo(currentPage + 1)}
              disabled={currentPage >= totalPages}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1.5 rounded border border-zinc-700 hover:border-zinc-600 transition-colors"
            >
              Próxima <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
