import type { LucideIcon } from "lucide-react";

export function MetricCard({ icon: Icon, label, value, detail, tone }: { icon: LucideIcon; label: string; value: string; detail: string; tone: string }) {
  return <article className="metric-card"><div className={`metric-icon tone-${tone}`}><Icon size={20} /></div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>;
}

export function PanelHeader({ icon: Icon, title, subtitle, badge }: { icon: LucideIcon; title: string; subtitle: string; badge?: string }) {
  return <div className="panel-header"><div className="panel-title-icon"><Icon size={18} /></div><div><h3>{title}</h3><p>{subtitle}</p></div>{badge && <span className="panel-badge">{badge}</span>}</div>;
}

export function EmptyState({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return <div className="empty-state"><Icon size={26} /><strong>{title}</strong><p>{text}</p></div>;
}
