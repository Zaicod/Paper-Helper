export interface User { id: number; username: string; email: string; created_at: string }
export interface CsrfToken { token: string; header_name: string }
export interface Collection { id: number; name: string; description: string; paper_count: number }
export interface CollectionPage { collections: Collection[]; total: number; page: number; size: number }
export interface PaperInput {
  source: string; paper_id: string; title: string; abstract: string; authors: string[]; categories: string[];
  published?: string | null; page_url: string; pdf_url?: string | null; cited_by_count?: number | null
}
export interface Paper extends PaperInput { id: number; added_at: string; note: string; metadata_edited?: boolean }
export type PaperSource = 'auto' | 'arxiv' | 'openalex' | 'crossref'
export interface SearchKeyword { text: string; match_mode: 'exact' | 'fuzzy' }
export type PaperSort = 'relevance' | 'latest' | 'citations'
export interface PaperSearchResult { contract_version: 1; query: string; requested_source: PaperSource; used_source: string; papers: PaperInput[]; keywords?: SearchKeyword[]; warnings?: { source: string; code: string; message: string }[]; page?: number; page_size?: number; total?: number; has_next?: boolean; sort?: PaperSort }
export interface CollectionDetail extends Collection { overall_note: string; papers: Paper[] }
export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'interrupted'
export type TaskCategory = 'active' | 'unfinished' | 'history'
export interface TaskInput {
  task_type?: 'research' | 'study_report'; learning_goal?: string; reflection?: string;
  idempotency_key: string; topic: string; mode: 'demo' | 'live'; limit: number; rag: 'none' | 'abstract';
  provider?: 'qwen' | 'openai'; model?: string; collection_id?: number; paper_ids?: number[]
}
export interface TaskSummary { task_id: string; topic: string; task_type?: 'research' | 'study_report'; status: TaskStatus; created_at: string; updated_at: string }
export interface StageEvent { stage: string; status: string; paper_id: string | null; message: string; timestamp: string }
export interface Analysis {
  paper_id: string; title: string; research_problem: string; innovation_points: string[]; methods: string[];
  results: string[]; limitations: string[]; evidence_notes: string[]; datasets: string[]; citations: string[]
}
export interface ResearchIdea {
  title: string; target_gap: string; hypothesis: string; proposed_method: string[]; expected_contribution: string;
  evaluation_plan: string[]; risks: string[]; related_paper_ids: string[]
}
export interface Report {
  topic: string; generated_at: string; papers: PaperInput[]; analyses: Analysis[];
  synthesis: { topic: string; overview: string; method_taxonomy: string[]; common_findings: string[]; disagreements: string[]; research_gaps: string[]; evidence_map: string[] };
  idea_portfolio: { topic: string; ideas: ResearchIdea[]; caution: string };
  analysis_failures: { paper_id: string; stage: string; error_type: string; retry_count: number; message: string }[];
  context_audits: { paper_id: string; query: string; selected_chunk_ids: string[]; dropped_count: number; estimated_tokens: number; token_budget: number; source_mode: string; decisions: { action: string; confidence: number; source: string }[] }[]
}
export interface StudyReport {
  report_type: 'study_report'; topic: string; generated_at: string; papers: PaperInput[];
  analyses: { paper_id: string; title: string; overview: string; background: string;
    methods: { name: string; purpose: string; inputs: string; outputs: string }[];
    innovations: string[]; results: string[]; reflection: string[];
    citations: { chunk_id: string; page_number: number | null; source_url: string }[] }[];
  synthesis: string[]; learning_plan: string[]; evidence_mode: 'pdf'; mode: 'live' | 'demo'
}
export interface Task extends TaskSummary { events: StageEvent[]; report: Report | StudyReport | null; error_code: string | null; error_message: string | null; sync_error: string | null }
export interface TaskPage { tasks: TaskSummary[]; total: number; page: number; size: number }

export type ModelProvider = 'qwen' | 'openai'
export interface ProviderSettings { provider: ModelProvider; model: string; configured: boolean; key_hint: string | null }
export interface ModelSettings { default_provider: ModelProvider | null; providers: ProviderSettings[] }
