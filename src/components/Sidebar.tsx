"use client";

import Link from "next/link";
import { FolderOpen, LayoutDashboard, Settings, UserSearch, FileText, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/app";
import { usePathname } from "next/navigation";

export function Sidebar() {
  const { toggleCopiloto } = useAppStore();
  const pathname = usePathname();

  return (
    <div className="w-64 border-r border-zinc-800 bg-zinc-950/50 flex flex-col h-screen sticky top-0">
      <div className="p-6">
        <h2 className="text-xl font-bold tracking-tight bg-gradient-to-r from-blue-400 to-blue-200 bg-clip-text text-transparent">
          Escrivão AI
        </h2>
        <p className="text-xs text-zinc-500 uppercase tracking-widest mt-1">Investigação</p>
      </div>

      <nav className="flex-1 px-4 space-y-2">
        <NavItem href="/" icon={<LayoutDashboard size={18} />} label="Dashboard" active={pathname === "/"} />
        <NavItem href="/inqueritos" icon={<FolderOpen size={18} />} label="Inquéritos" active={pathname.startsWith("/inquerito")} />
        <NavItem href="/agentes/osint" icon={<UserSearch size={18} />} label="Agente OSINT" active={pathname === "/agentes/osint"} />
        <NavItem href="#" icon={<FileText size={18} />} label="Cautelares" />
      </nav>

      <div className="p-4 border-t border-zinc-800 mt-auto space-y-2">
        <button
          onClick={toggleCopiloto}
          className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors text-blue-400 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20"
        >
          <div className="flex items-center gap-3">
            <Bot size={18} />
            <span>Copiloto</span>
          </div>
          <kbd className="text-[10px] uppercase bg-blue-950 px-1.5 py-0.5 rounded text-blue-300">Ctrl+Space</kbd>
        </button>
        <NavItem href="#" icon={<Settings size={18} />} label="Configurações" />
      </div>
    </div>
  );
}

function NavItem({ href, icon, label, active = false }: { href: string; icon: React.ReactNode; label: string; active?: boolean }) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
        active 
          ? "bg-blue-500/10 text-blue-400" 
          : "text-zinc-400 hover:text-zinc-50 hover:bg-zinc-800/50"
      )}
    >
      {icon}
      {label}
    </Link>
  );
}
