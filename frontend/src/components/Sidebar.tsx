"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    { href: "/", label: "Command Center", meta: "CHAT" },
    { href: "/pulse", label: "Proactive Pulse", meta: "INTEL" },
    { href: "/tracking", label: "Surveillance", meta: "WATCH" },
    { href: "/draft", label: "Waiver Wire", meta: "WAIVERS" },
    { href: "/roster", label: "Roster Audit", meta: "TEAM" },
  ];

  return (
    <aside style={styles.aside}>
      <div style={styles.brandSection}>
        <div style={styles.brandTitle} className="font-mono">
          GRIDIRON AI
        </div>
        <div style={styles.leagueName}>WA minus Josh</div>
        <div style={styles.teamTag}>
          <span className="status-dot healthy" />
          <span style={styles.teamText}>Team Cooper (ID 2)</span>
        </div>
      </div>

      <nav style={styles.nav}>
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                ...styles.navLink,
                ...(isActive ? styles.navLinkActive : {}),
              }}
            >
              <span style={styles.navLabel}>{item.label}</span>
              <span style={styles.navMeta} className="font-mono">
                {item.meta}
              </span>
            </Link>
          );
        })}
      </nav>

      <div style={styles.footer}>
        <div style={styles.footerRow} className="font-mono">
          <span style={styles.footerLabel}>STATUS</span>
          <span style={styles.footerVal}>
            <span className="status-dot healthy" style={{ marginRight: "6px" }} />
            READY
          </span>
        </div>
        <div style={styles.footerRow} className="font-mono">
          <span style={styles.footerLabel}>SCORING</span>
          <span style={styles.footerVal}>10T PPR (3WR)</span>
        </div>
        <div style={styles.footerRow} className="font-mono">
          <span style={styles.footerLabel}>VERSION</span>
          <span style={styles.footerVal}>v1.0.0</span>
        </div>
      </div>
    </aside>
  );
}

const styles: Record<string, React.CSSProperties> = {
  aside: {
    width: "230px",
    minWidth: "230px",
    height: "100vh",
    backgroundColor: "var(--bg-raised)",
    borderRight: "1px solid var(--border-subtle)",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    userSelect: "none",
  },
  brandSection: {
    padding: "var(--space-5) var(--space-4) var(--space-4)",
    borderBottom: "1px solid var(--border-subtle)",
  },
  brandTitle: {
    fontSize: "12px",
    fontWeight: 700,
    letterSpacing: "0.1em",
    color: "var(--accent-amber)",
    marginBottom: "var(--space-1)",
  },
  leagueName: {
    fontSize: "14px",
    fontWeight: 600,
    color: "var(--text-primary)",
    marginBottom: "var(--space-2)",
  },
  teamTag: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
    fontSize: "12px",
    color: "var(--text-muted)",
  },
  teamText: {
    color: "var(--text-secondary)",
  },
  nav: {
    display: "flex",
    flexDirection: "column",
    padding: "var(--space-3) 0",
    flex: 1,
  },
  navLink: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "var(--space-3) var(--space-4)",
    fontSize: "13px",
    color: "var(--text-muted)",
    borderLeftWidth: "3px",
    borderLeftStyle: "solid",
    borderLeftColor: "transparent",
    transition: "background-color 100ms ease, color 100ms ease",
  },
  navLinkActive: {
    backgroundColor: "var(--bg-surface)",
    borderLeftColor: "var(--accent-amber)",
    color: "var(--text-primary)",
    fontWeight: 500,
  },
  navLabel: {
    letterSpacing: "-0.01em",
  },
  navMeta: {
    fontSize: "10px",
    color: "var(--text-dim)",
    letterSpacing: "0.05em",
  },
  footer: {
    padding: "var(--space-3) var(--space-4)",
    borderTop: "1px solid var(--border-subtle)",
    backgroundColor: "var(--bg-base)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-2)",
  },
  footerRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
  },
  footerLabel: {
    color: "var(--text-dim)",
  },
  footerVal: {
    color: "var(--text-secondary)",
    display: "flex",
    alignItems: "center",
  },
};
