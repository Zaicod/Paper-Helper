import { useEffect, useMemo, useRef, useState } from "react";
import { Layers3, LoaderCircle } from "lucide-react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { ApiError, getCollections, getMe, getPapers, getTask, logout, startResearch, websocketUrl } from "./api";
import { AuthScreen } from "./components/AuthScreen";
import { DashboardLayout } from "./components/DashboardLayout";
import { CollectionsPage } from "./pages/CollectionsPage";
import { LibraryPage } from "./pages/LibraryPage";
import { ResearchPage } from "./pages/ResearchPage";
import { TasksPage } from "./pages/TasksPage";
import { SettingsPage } from "./pages/SettingsPage";
import type { CollectionItem, PaperItem, ResearchRequest, TaskEvent, TaskView, User } from "./types";

function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [task, setTask] = useState<TaskView | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [papers, setPapers] = useState<PaperItem[]>([]);
  const [collections, setCollections] = useState<CollectionItem[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const completedNodes = useMemo(() => new Set(events.filter((event) => event.type === "node").map((event) => event.node)), [events]);
  const progress = task?.status === "completed" ? 100 : Math.round((completedNodes.size / 6) * 100);

  async function refreshLibrary(query = "") {
    setLoadingLibrary(true);
    try {
      const [paperData, collectionData] = await Promise.all([getPapers(query), getCollections()]);
      setPapers(paperData); setCollections(collectionData);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "资料库加载失败"); }
    finally { setLoadingLibrary(false); }
  }

  useEffect(() => {
    getMe().then(setUser).catch((caught) => {
      setUser(null);
      if (caught instanceof Error && (!(caught instanceof ApiError) || caught.status !== 401)) setAuthError(caught.message);
    }).finally(() => setAuthLoading(false));
    return () => socketRef.current?.close();
  }, []);

  useEffect(() => { if (user) void refreshLibrary(); }, [user]);

  async function start(request: ResearchRequest) {
    socketRef.current?.close(); setEvents([]); setError(null);
    try {
      const created = await startResearch(request);
      setTask(created); navigate("/tasks");
      const socket = new WebSocket(websocketUrl(created.task_id)); socketRef.current = socket;
      socket.onmessage = async ({ data }) => {
        const incoming = JSON.parse(data) as TaskEvent;
        setEvents((current) => [...current, incoming]);
        if (incoming.type === "completed" || incoming.type === "error") {
          const detail = await getTask(created.task_id); setTask(detail);
          if (incoming.type === "completed") await refreshLibrary();
        }
      };
      socket.onerror = () => setError("实时连接失败，请刷新后重试");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "研究任务启动失败"); }
  }

  async function handleLogout() {
    try { await logout(); }
    finally { socketRef.current?.close(); setUser(null); setTask(null); setEvents([]); setPapers([]); navigate("/"); }
  }

  if (authLoading) return <div className="auth-loading"><div className="auth-logo"><Layers3 size={25} /></div><LoaderCircle className="spin" size={22} /><span>正在恢复 Redis 登录会话…</span></div>;
  if (!user) return <AuthScreen initialError={authError} onAuthenticated={(authenticated) => { setAuthError(null); setUser(authenticated); }} />;

  return <Routes><Route element={<DashboardLayout user={user} error={error} onClearError={() => setError(null)} onLogout={() => void handleLogout()} />}><Route index element={<ResearchPage papers={papers} collections={collections} task={task} progress={progress} onStart={start} />} /><Route path="library" element={<LibraryPage papers={papers} collections={collections} loading={loadingLibrary} onRefresh={refreshLibrary} onError={setError} />} /><Route path="tasks" element={<TasksPage task={task} events={events} />} /><Route path="collections" element={<CollectionsPage collections={collections} onRefresh={() => refreshLibrary()} onError={setError} />} /><Route path="settings" element={<SettingsPage user={user} onError={setError} />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes>;
}

export default App;
