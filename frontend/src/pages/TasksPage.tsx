import { Activity, Check, Clock3, Download, FileText, FlaskConical, LoaderCircle, Network, Search, X } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState, PanelHeader } from "../components/ui";
import type { TaskEvent, TaskView } from "../types";

const pipeline = [
  { id: "search", label: "文献搜索", hint: "Fixture 检索与分类过滤", icon: Search },
  { id: "analyze", label: "逐篇分析", hint: "问题、方法、结果与局限", icon: FlaskConical },
  { id: "synthesize", label: "领域综合", hint: "跨论文归纳与研究空白", icon: Network },
  { id: "ideate", label: "研究构思", hint: "基于研究空白提出可验证想法", icon: FlaskConical },
  { id: "render", label: "报告渲染", hint: "统一领域模型，多种格式", icon: FileText },
  { id: "persist", label: "资料入库", hint: "元数据去重与分析留档", icon: Activity },
];

export function TasksPage({ task, events }: { task: TaskView | null; events: TaskEvent[] }) {
  const completed = new Set(events.filter((event) => event.type === "node").map((event) => event.node)); const running = task?.status === "queued" || task?.status === "running"; const count = pipeline.filter((step) => completed.has(step.id)).length; const active = running ? pipeline[count]?.id : null; const progress = task?.status === "completed" ? 100 : Math.round((count / pipeline.length) * 100);
  if (!task) return <section className="panel standalone-empty"><EmptyState icon={Clock3} title="还没有研究任务" text="从研究工作台启动一次任务后，这里会独立展示执行图和实时事件。" /><Link className="primary-link" to="/">创建研究任务</Link></section>;
  return <div className="workspace-grid page-workspace"><section className="panel pipeline-panel"><PanelHeader icon={Network} title="工作流执行" subtitle={`任务 ${task.task_id.slice(0, 8)}`} badge={running ? "运行中" : task.status === "completed" ? "已完成" : "失败"} /><div className="progress-track"><span style={{ width: `${progress}%` }} /></div><div className="pipeline-list">{pipeline.map(({ id, label, hint, icon: Icon }, index) => { const done = completed.has(id); const isActive = active === id; return <div className={`pipeline-step ${done ? "done" : ""} ${isActive ? "active" : ""}`} key={id}><div className="step-rail"><div className="step-icon">{done ? <Check size={17} /> : isActive ? <LoaderCircle className="spin" size={17} /> : <Icon size={17} />}</div>{index < pipeline.length - 1 && <span />}</div><div className="step-copy"><strong>{label}</strong><p>{hint}</p></div><span className="step-status">{done ? "完成" : isActive ? "执行中" : "等待"}</span></div>; })}</div></section><section className="panel activity-panel"><PanelHeader icon={Activity} title="实时事件" subtitle="WebSocket event stream" /><div className="event-stream">{events.length === 0 ? <EmptyState icon={Clock3} title="等待首个事件" text="节点状态会实时显示在这里。" /> : events.slice().reverse().map((item, index) => <div className="event-item" key={`${item.timestamp}-${index}`}><span className={`event-mark event-${item.type}`}>{item.type === "completed" ? <Check size={14} /> : item.type === "error" ? <X size={14} /> : <Activity size={14} />}</span><div><strong>{item.node ?? (item.type === "completed" ? "任务完成" : "研究任务")}</strong><p>{item.message}</p></div><time>{new Date(item.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time></div>)}</div>{task.artifacts && task.artifacts.length > 0 && <div className="artifact-box"><span>研究产物</span>{task.artifacts.map((url, index) => <a href={url} key={url}><Download size={15} />{task.files[index]}</a>)}</div>}</section></div>;
}
