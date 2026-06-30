"use client";

import type { ReactNode } from "react";

type IconProps = {
  children: ReactNode;
  className?: string;
  tone?: "blue" | "green" | "orange" | "red" | "purple" | "slate";
};

function IconShell({ children, className = "", tone = "blue" }: IconProps) {
  return (
    <span className={`product-icon ${tone} ${className}`} aria-hidden="true">
      {children}
    </span>
  );
}

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

export function ProductIcon({ className, name, tone }: { className?: string; name: string; tone?: IconProps["tone"] }) {
  const icons: Record<string, ReactNode> = {
    dashboard: (
      <Svg>
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <path d="M14 17h7" />
        <path d="M14 21h7" />
      </Svg>
    ),
    customerLines: (
      <Svg>
        <rect x="4" y="4" width="6" height="6" rx="1.5" />
        <rect x="14" y="4" width="6" height="6" rx="1.5" />
        <rect x="4" y="14" width="6" height="6" rx="1.5" />
        <rect x="14" y="14" width="6" height="6" rx="1.5" />
      </Svg>
    ),
    builder: (
      <Svg>
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="18" cy="6" r="2.5" />
        <circle cx="12" cy="18" r="2.5" />
        <path d="M8.2 7.4 10.8 16" />
        <path d="m15.8 7.4-2.6 8.6" />
        <path d="M8.5 6h7" />
      </Svg>
    ),
    lines: (
      <Svg>
        <path d="M5 7h11" />
        <path d="m13 4 3 3-3 3" />
        <path d="M19 17H8" />
        <path d="m11 14-3 3 3 3" />
      </Svg>
    ),
    servers: (
      <Svg>
        <rect x="4" y="4" width="16" height="6" rx="2" />
        <rect x="4" y="14" width="16" height="6" rx="2" />
        <path d="M8 7h.01" />
        <path d="M8 17h.01" />
      </Svg>
    ),
    tasks: (
      <Svg>
        <path d="M8 3h8l4 4v14H4V3h4Z" />
        <path d="M16 3v5h4" />
        <path d="M8 12h8" />
        <path d="M8 16h6" />
      </Svg>
    ),
    settings: (
      <Svg>
        <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
        <path d="M19.4 15a1.8 1.8 0 0 0 .36 1.98l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.8 1.8 0 0 0 15 19.4a1.8 1.8 0 0 0-1 .6 1.8 1.8 0 0 0-.46 1.35V21a2 2 0 1 1-4 0v-.09A1.8 1.8 0 0 0 8.6 19.4a1.8 1.8 0 0 0-1.98.36l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.8 1.8 0 0 0 4.6 15a1.8 1.8 0 0 0-.6-1 1.8 1.8 0 0 0-1.35-.46H3a2 2 0 1 1 0-4h.09A1.8 1.8 0 0 0 4.6 8.6a1.8 1.8 0 0 0-.36-1.98l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.8 1.8 0 0 0 9 4.6a1.8 1.8 0 0 0 1-.6 1.8 1.8 0 0 0 .46-1.35V3a2 2 0 1 1 4 0v.09A1.8 1.8 0 0 0 15.4 4.6a1.8 1.8 0 0 0 1.98-.36l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.8 1.8 0 0 0 19.4 9c.3.31.79.6 1.35.6H21a2 2 0 1 1 0 4h-.09a1.8 1.8 0 0 0-1.51 1.4Z" />
      </Svg>
    ),
    debug: (
      <Svg>
        <path d="M8 9l-4 3 4 3" />
        <path d="M16 9l4 3-4 3" />
        <path d="M14 5l-4 14" />
      </Svg>
    ),
    bell: (
      <Svg>
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </Svg>
    ),
    help: (
      <Svg>
        <circle cx="12" cy="12" r="9" />
        <path d="M9.5 9a2.5 2.5 0 0 1 4.5 1.5c0 2-2 2-2 4" />
        <path d="M12 18h.01" />
      </Svg>
    ),
    search: (
      <Svg>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </Svg>
    ),
    user: (
      <Svg>
        <circle cx="12" cy="8" r="4" />
        <path d="M5 21a7 7 0 0 1 14 0" />
      </Svg>
    ),
    server: (
      <Svg>
        <path d="M6 3h12l2 5H4l2-5Z" />
        <path d="M4 8v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V8" />
        <path d="M8 13h8" />
      </Svg>
    ),
    route: (
      <Svg>
        <circle cx="6" cy="6" r="3" />
        <circle cx="18" cy="18" r="3" />
        <path d="M8.5 8.5l7 7" />
      </Svg>
    ),
    platform: (
      <Svg>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18" />
        <path d="M12 3a14 14 0 0 1 0 18" />
        <path d="M12 3a14 14 0 0 0 0 18" />
      </Svg>
    ),
    alert: (
      <Svg>
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      </Svg>
    ),
    action: (
      <Svg>
        <path d="m13 2-8 12h6l-1 8 8-12h-6l1-8Z" />
      </Svg>
    ),
    bulb: (
      <Svg>
        <path d="M9 18h6" />
        <path d="M10 22h4" />
        <path d="M8.5 14.5a6 6 0 1 1 7 0c-.8.6-1.5 1.7-1.5 3.5h-4c0-1.8-.7-2.9-1.5-3.5Z" />
      </Svg>
    ),
    document: (
      <Svg>
        <path d="M6 3h8l4 4v14H6V3Z" />
        <path d="M14 3v5h4" />
        <path d="M9 13h6" />
        <path d="M9 17h5" />
      </Svg>
    ),
    shield: (
      <Svg>
        <path d="M12 3 19 6v5c0 4.4-2.8 8.4-7 10-4.2-1.6-7-5.6-7-10V6l7-3Z" />
        <path d="m9 12 2 2 4-5" />
      </Svg>
    ),
    clock: (
      <Svg>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v6l4 2" />
      </Svg>
    ),
    activity: (
      <Svg>
        <path d="M3 12h4l2-6 4 12 2-6h6" />
      </Svg>
    ),
    eye: (
      <Svg>
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
      </Svg>
    ),
    arrow: (
      <Svg>
        <path d="M5 12h14" />
        <path d="m13 6 6 6-6 6" />
      </Svg>
    ),
  };

  return <IconShell className={className} tone={tone}>{icons[name] ?? icons.dashboard}</IconShell>;
}

export function PlatformIcon({ platform }: { platform: string }) {
  const lower = platform.toLowerCase();
  const label = lower.includes("facebook") ? "F" : lower.includes("tiktok") ? "TK" : lower.includes("youtube") ? "▶" : lower.includes("meta") ? "M" : "-";
  const tone = lower.includes("youtube") ? "red" : lower.includes("tiktok") ? "slate" : lower.includes("facebook") || lower.includes("meta") ? "blue" : "slate";
  return (
    <span className={`platform-icon ${tone}`} aria-hidden="true">
      {label}
    </span>
  );
}
