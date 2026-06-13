"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import clsx from "clsx";

const NAV = [
  { href: "/",           label: "Dashboard",  icon: "⬡" },
  { href: "/users",      label: "Users",       icon: "👤" },
  { href: "/requests",   label: "Requests",    icon: "📬" },
  { href: "/network",    label: "Network",     icon: "🕸" },
  { href: "/analytics",  label: "Analytics",   icon: "📊" },
];

export default function Navbar() {
  const path = usePathname();
  const [dark, setDark] = useState(true);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <nav className="fixed top-0 left-0 right-0 z-40 h-14 bg-surface-800/90 backdrop-blur border-b border-white/5 flex items-center px-4 gap-1">
      <span className="text-brand-400 font-bold text-lg mr-4 tracking-tight select-none">
        SocialGraph
      </span>
      <div className="flex items-center gap-1 flex-1">
        {NAV.map(n => (
          <Link
            key={n.href}
            href={n.href}
            className={clsx(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-all",
              path === n.href
                ? "bg-brand-600 text-white"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            )}
          >
            <span className="mr-1.5">{n.icon}</span>{n.label}
          </Link>
        ))}
      </div>
      <button
        onClick={() => setDark(d => !d)}
        className="ml-auto text-gray-400 hover:text-white text-lg px-2 transition-colors"
        title="Toggle dark mode"
      >
        {dark ? "☀" : "🌙"}
      </button>
    </nav>
  );
}
