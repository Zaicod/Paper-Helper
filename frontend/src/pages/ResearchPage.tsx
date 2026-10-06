import { FormEvent, useEffect, useState } from "react";
import { Activity, BookOpen, Check, FlaskConical, FolderKanban, LoaderCircle, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { getCollection } from "../api";
import { MetricCard } from "../components/ui";
import type { CollectionDetail, CollectionItem, PaperItem, ResearchRequest, TaskView } from "../types";

export function ResearchPage({ papers, collections, task, progress, onStart }: {
  papers: PaperItem[];
  collections: CollectionItem[];
  task: TaskView | null;
  progress: number;
  onStart: (request: ResearchRequest) => Promise<void>;
}) {
  const [topic, setTopic] = useState("retrieval augmented generation");
  const [collectionId, setCollectionId] = useState<number | null>(collections[0]?.id ?? null);
  const [collection, setCollection] = useState<CollectionDetail | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const running = task?.status === "queued" || task?.status === "running";

  useEffect(() => {
    if (collectionId === null && collections.length) setCollectionId(collections[0].id);
  }, [collectionId, collections]);

  useEffect(() => {
    if (collectionId === null) { setCollection(null); return; }
    let active = true;
    setLoading(true);
    getCollection(collectionId).then((value) => {
      if (!active) return;
      setCollection(value);
      setSelected(new Set(value.papers.map((paper) => `${paper.source}\u0000${paper.paper_id}`)));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [collectionId]);

  function toggle(key: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!topic.trim() || !collection || !selected.size || running) return;
    await onStart({
      topic: topic.trim(), limit: selected.size, category: null, collection_id: collection.id,
      selected_papers: collection.papers.filter((paper) => selected.has(`${paper.source}\u0000${paper.paper_id}`)).map(({ source, paper_id }) => ({ source, paper_id })),
    });
  }

  return <>
    <section className="hero-card page-hero collection-research-hero">
      <div className="hero-orb orb-one" /><div className="hero-orb orb-two" />
      <div className="hero-copy"><span className="hero-kicker"><Sparkles size={15} /> COLLECTION RESEARCH AGENT</span><h2>从收藏夹出发，<br /><em>把论文变成研究结论</em></h2><p>研究分类与收藏夹保持一致。你明确选择证据范围，LangGraph 负责分析、跨论文归纳与报告生成。</p></div>
      <form className="research-form" onSubmit={submit}>
        <label htmlFor="collection">研究收藏夹</label><select id="collection" value={collectionId ?? ""} onChange={(event) => setCollectionId(event.target.value ? Number(event.target.value) : null)}><option value="">选择收藏夹</option>{collections.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.paper_count} 篇</option>)}</select>
        <label htmlFor="topic">本次研究方向</label><input id="topic" value={topic} onChange={(event) => setTopic(event.target.value)} maxLength={200} placeholder="例如：RAG 的事实一致性评估" />
        <div className="paper-picker-head"><span>选择参与分析的论文</span>{collection && <button type="button" className="text-button" onClick={() => setSelected(new Set(collection.papers.map((paper) => `${paper.source}\u0000${paper.paper_id}`)))}>全选</button>}</div>
        <div className="paper-picker compact">{loading ? <span className="picker-empty"><LoaderCircle className="spin" size={17} />加载论文…</span> : collection?.papers.length ? collection.papers.map((paper) => { const key = `${paper.source}\u0000${paper.paper_id}`; return <label key={key} className={selected.has(key) ? "picked" : ""}><input type="checkbox" checked={selected.has(key)} onChange={() => toggle(key)} /><span><strong>{paper.title}</strong><small>添加于 {new Date(paper.added_at).toLocaleDateString("zh-CN")}</small></span></label>; }) : <span className="picker-empty">该收藏夹还没有论文</span>}</div>
        <button className="primary-button" disabled={running || !selected.size} type="submit"><Sparkles size={19} />{running ? "研究进行中" : `分析所选 ${selected.size} 篇论文`}</button><p className="form-note"><Check size={14} />生成的研究任务会关联回当前收藏夹</p>
      </form>
    </section>
    <section className="metrics-grid"><MetricCard icon={BookOpen} label="论文总数" value={papers.length.toString()} detail="已去重入库" tone="blue" /><MetricCard icon={FlaskConical} label="累计分析" value={papers.reduce((sum, paper) => sum + paper.analysis_count, 0).toString()} detail="结构化记录" tone="violet" /><MetricCard icon={FolderKanban} label="收藏夹" value={collections.length.toString()} detail="研究分类" tone="amber" /><MetricCard icon={Activity} label="当前任务" value={`${progress}%`} detail={task?.status ?? "等待任务"} tone="green" /></section>
    <section className="page-links"><Link to="/library"><BookOpen size={20} /><div><strong>发现与管理论文</strong><span>关键词搜索、PDF 下载和资料入库</span></div></Link><Link to="/tasks"><Activity size={20} /><div><strong>查看研究任务</strong><span>LangGraph 节点和实时事件</span></div></Link><Link to="/collections"><FolderKanban size={20} /><div><strong>收藏夹知识工作区</strong><span>论文笔记、整体归纳与思维导图</span></div></Link></section>
  </>;
}
