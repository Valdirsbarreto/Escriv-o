"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderOpen, CalendarDays, Mic, Bot, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/app";

const items = [
  { href: "/", icon: FolderOpen, label: "IPs" },
  { href: "/intimacoes", icon: CalendarDays, label: "Intimações" },
  { href: "/oitiva", icon: Mic, label: "Oitiva" },
  { href: "/admin", icon: ShieldAlert, label: "Admin" },
];

export function MobileNav() {
  const pathname = usePathname();
  const { toggleCopiloto } = useAppStore();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-950 border-t border-zinc-800 flex md:hidden safe-area-bottom">
      {items.map(({ href, icon: Icon, label }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "flex-1 flex flex-col items-center justify-center py-2 gap-0.5 text-xs transition-colors",
            pathname === href
              ? "text-blue-400"
              : "text-zinc-500 hover:text-zinc-300"
          )}
        >
          <Icon size={20} />
          <span>{label}</span>
        </Link>
      ))}
      <button
        onClick={toggleCopiloto}
        className="flex-1 flex flex-col items-center justify-center py-2 gap-0.5 text-xs text-zinc-500 hover:text-blue-400 transition-colors"
      >
        <Bot size={20} />
        <span>Copiloto</span>
      </button>
    </nav>
  );
}
