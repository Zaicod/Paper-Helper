import { useState } from "react";
import { Activity, BookOpen, ChevronRight, Circle, Code2, FolderKanban, Layers3, LogOut, Menu, Sparkles, X, Zap } from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import type { User } from "../types";

const navigation = [
  { path: "/", label: "研究工作台", icon: Sparkles },
  { path: "/library", label: "论文资料库", icon: BookOpen },
  { path: "/tasks", label: "研究任务", icon: Activity },
  { path: "/collections", label: "收藏夹", icon: FolderKanban },
];

const titles: Record<string, string> = { "/": "研究工作台", "/library": "论文资料库", "/tasks": "研究任务", "/collections": "收藏夹", "/settings": "个人设置" };

export function DashboardLayout({ user, error, onClearError, onLogout }: { user: User; error: string | null; onClearError: () => void; onLogout: () => void }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  return <div className="app-shell"><aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}><div className="brand"><div className="brand-mark"><Layers3 size={22} /></div><div><strong>PaperFlow</strong><span>Research OS</span></div><button className="icon-button sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="关闭菜单"><X size={20} /></button></div><nav><p className="nav-caption">工作空间</p>{navigation.map(({ path, label, icon: Icon }) => <NavLink end={path === "/"} to={path} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`} onClick={() => setSidebarOpen(false)} key={path}><Icon size={18} /><span>{label}</span><ChevronRight size={16} /></NavLink>)}</nav><div className="sidebar-insight"><div className="insight-icon"><Zap size={18} /></div><strong>Redis 持久会话</strong><p>登录状态由 Redis TTL 管理，页面模块使用 React Router 独立导航。</p><span className="status-dot"><i />服务已连接</span></div><a className="github-link" href="https://github.com/Zaicod/Paper-Helper" target="_blank" rel="noreferrer"><Code2 size={17} />查看项目源码<ChevronRight size={15} /></a></aside>{sidebarOpen && <button className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="关闭菜单" />}<main className="main-content"><header className="topbar"><button className="icon-button menu-button" onClick={() => setSidebarOpen(true)} aria-label="打开菜单"><Menu size={21} /></button><div><p className="eyebrow">AI RESEARCH WORKSPACE</p><h1>{titles[location.pathname] ?? "PaperFlow"}</h1></div><div className="topbar-meta"><span><Circle size={8} fill="currentColor" /> API Online</span><div className="user-menu"><Link className="user-settings-link" to="/settings" aria-label="进入个人设置" title="个人设置"><div className="avatar">{user.username.slice(0, 1).toUpperCase()}</div><div className="user-copy"><strong>{user.username}</strong><small>模型与密钥设置</small></div></Link><button onClick={onLogout} aria-label="退出登录" title="退出登录"><LogOut size={17} /></button></div></div></header>{error && <div className="error-banner"><X size={18} /><span>{error}</span><button onClick={onClearError}>关闭</button></div>}<Outlet /><footer><span>PaperFlow · Teaching-first Agent Engineering Project</span><span>LangGraph · FastAPI · Redis · SQLAlchemy</span></footer></main></div>;
}
