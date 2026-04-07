"use client";

import Link from "next/link";
import { FolderOpen, LayoutDashboard, UserSearch, Bot, UploadCloud, CalendarDays, ShieldAlert, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/app";
import { usePathname } from "next/navigation";

export function Sidebar() {
  const { toggleCopiloto, sidebarCollapsed } = useAppStore();
  const pathname = usePathname();

  return (
    <div
      className={cn(
        "border-r border-zinc-800 bg-zinc-950/50 flex flex-col h-screen sticky top-0 shrink-0 transition-all duration-300 ease-in-out overflow-hidden",
        sidebarCollapsed ? "w-[60px]" : "w-64"
      )}
    >
      {/* Branding */}
      <div className={cn("p-4 transition-all duration-300", sidebarCollapsed ? "px-3" : "px-6 pt-6")}>
        {sidebarCollapsed ? (
          <div className="w-8 h-8 rounded-lg bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
            <ChevronRight size={14} className="text-blue-400" />
          </div>
        ) : (
          <>
            <h2 className="text-xl font-bold tracking-tight bg-gradient-to-r from-blue-400 to-blue-200 bg-clip-text text-transparent">
              Escrivão AI
            </h2>
            <p className="text-xs text-zinc-500 uppercase tracking-widest mt-1">Investigação</p>
          </>
        )}
      </div>

      {/* Importar Documento */}
      <div className={cn("mb-2 transition-all duration-300", sidebarCollapsed ? "px-2" : "px-4")}>
        <Link
          href="/ingestao"
          title="Importar Documento"
          className={cn(
            "flex items-center gap-3 rounded-lg text-sm font-semibold transition-all",
            sidebarCollapsed ? "px-2 py-2.5 justify-center" : "px-3 py-2.5",
            pathname === "/ingestao"
              ? "bg-blue-500 text-white shadow-lg shadow-blue-500/30"
              : "bg-blue-500/10 text-blue-300 hover:bg-blue-500/20 border border-blue-500/20"
          )}
        >
          <UploadCloud size={18} className="shrink-0" />
          {!sidebarCollapsed && <span>Importar Documento</span>}
        </Link>
      </div>

      {/* Nav */}
      <nav className={cn("flex-1 space-y-1 transition-all duration-300", sidebarCollapsed ? "px-2" : "px-4")}>
        <NavItem href="/" icon={<FolderOpen size={18} />} label="Inquéritos" active={pathname === "/"} collapsed={sidebarCollapsed} />
        <NavItem href="/agentes/osint" icon={<UserSearch size={18} />} label="Agente OSINT" active={pathname === "/agentes/osint"} collapsed={sidebarCollapsed} />
        <NavItem href="/intimacoes" icon={<CalendarDays size={18} />} label="Intimações" active={pathname === "/intimacoes"} collapsed={sidebarCollapsed} />
      </nav>

      {/* Footer */}
      <div className={cn("border-t border-zinc-800 mt-auto space-y-2 transition-all duration-300", sidebarCollapsed ? "p-2" : "p-4")}>
        <button
          onClick={toggleCopiloto}
          title="Copiloto"
          className={cn(
            "w-full flex items-center gap-3 rounded-md font-medium text-sm transition-colors text-blue-400 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20",
            sidebarCollapsed ? "px-2 py-2 justify-center" : "px-3 py-2 justify-between"
          )}
        >
          <div className="flex items-center gap-3">
            <Bot size={18} className="shrink-0" />
            {!sidebarCollapsed && <span>Copiloto</span>}
          </div>
          {!sidebarCollapsed && (
            <kbd className="text-[10px] uppercase bg-blue-950 px-1.5 py-0.5 rounded text-blue-300">Ctrl+Space</kbd>
          )}
        </button>
        <NavItem href="/admin" icon={<ShieldAlert size={18} />} label="Administrativo" active={pathname === "/admin"} collapsed={sidebarCollapsed} />
      </div>
    </div>
  );
}

function NavItem({
  href, icon, label, active = false, collapsed = false,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  collapsed?: boolean;
}) {
  return (
    <Link
      href={href}
      title={label}
      className={cn(
        "flex items-center gap-3 rounded-md text-sm font-medium transition-colors",
        collapsed ? "px-2 py-2 justify-center" : "px-3 py-2",
        active
          ? "bg-blue-500/10 text-blue-400"
          : "text-zinc-400 hover:text-zinc-50 hover:bg-zinc-800/50"
      )}
    >
      <span className="shrink-0">{icon}</span>
      {!collapsed && label}
    </Link>
  );
}
