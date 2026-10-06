export type Category = "cs.CL" | "cs.AI" | null;

export interface ResearchRequest {
  topic: string;
  limit: number;
  category: Category;
  collection_id: number | null;
  selected_papers: PaperReference[];
}

export interface PaperReference {
  source: string;
  paper_id: string;
}

export interface TaskView {
  task_id: string;
  status: "queued" | "running" | "completed" | "failed";
  request: ResearchRequest;
  files: string[];
  artifacts?: string[];
  library_run_id: string | null;
  error: string | null;
}

export interface TaskEvent {
  type: "task" | "node" | "completed" | "error";
  message: string;
  node: string | null;
  timestamp: string;
}

export interface PaperItem {
  source: string;
  paper_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  collections: string[];
  tags: string[];
  published: string | null;
  page_url: string;
  pdf_url: string | null;
  download_id: number | null;
  analysis_count: number;
}

export interface SearchPaper {
  source: string;
  paper_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  published: string | null;
  page_url: string;
  pdf_url: string | null;
}

export interface ImportedPaper extends PaperItem {
  local_download_url?: string;
}

export interface CollectionItem {
  id: number;
  name: string;
  description: string;
  paper_count: number;
}

export interface CollectionPaper {
  source: string;
  paper_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  published: string | null;
  page_url: string;
  pdf_url: string | null;
  added_at: string;
  note: string;
}

export interface MindMapNode {
  id: string;
  label: string;
  summary: string;
  level: number;
  paper_ids: string[];
}

export interface MindMapEdge {
  source: string;
  target: string;
  relationship: string;
}

export interface MindMapItem {
  id: number;
  collection_id: number;
  direction: string;
  date_from: string | null;
  date_to: string | null;
  generator: string;
  paper_ids: string[];
  map: { title: string; overview: string; nodes: MindMapNode[]; edges: MindMapEdge[] };
  created_at: string;
}

export interface CollectionDetail extends CollectionItem {
  overall_note: string;
  papers: CollectionPaper[];
  mind_maps: MindMapItem[];
  research_run_ids: string[];
}

export interface User {
  id: number;
  username: string;
  email: string;
  created_at: string;
}

export interface ProviderSetting {
  provider: string;
  label: string;
  base_url: string;
  has_api_key: boolean;
  api_key_hint: string | null;
  credential_source: "personal" | "environment" | "missing";
  models: string[];
}

export interface AgentModelSetting {
  agent_role: string;
  label: string;
  provider: string;
  model_name: string;
}

export interface UserModelSettings {
  providers: ProviderSetting[];
  agents: AgentModelSetting[];
  presets: Record<string, Record<string, { provider: string; model_name: string }>>;
}
