import type { CollectionDetail, CollectionItem, ImportedPaper, MindMapItem, PaperItem, PaperReference, ResearchRequest, SearchPaper, TaskView, User, UserModelSettings } from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(payload?.detail ?? `请求失败：HTTP ${response.status}`, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function startResearch(payload: ResearchRequest): Promise<TaskView> {
  return request("/api/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getTask(taskId: string): Promise<TaskView> {
  return request(`/api/tasks/${taskId}`);
}

export async function getPapers(query = ""): Promise<PaperItem[]> {
  const params = new URLSearchParams({ limit: "50" });
  if (query.trim()) params.set("query", query.trim());
  const payload = await request<{ papers: PaperItem[] }>(`/api/library/papers?${params}`);
  return payload.papers;
}

export async function getCollections(query = ""): Promise<CollectionItem[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  const suffix = params.size ? `?${params}` : "";
  const payload = await request<{ collections: CollectionItem[] }>(`/api/library/collections${suffix}`);
  return payload.collections;
}

export function deleteCollection(collectionId: number): Promise<void> {
  return request(`/api/library/collections/${collectionId}`, { method: "DELETE" });
}

export function createCollection(payload: { name: string; description: string }): Promise<CollectionItem> {
  return request("/api/library/collections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getCollection(collectionId: number): Promise<CollectionDetail> {
  return request(`/api/library/collections/${collectionId}`);
}

export function saveCollectionNote(collectionId: number, content: string): Promise<{ content: string }> {
  return request(`/api/library/collections/${collectionId}/note`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export function savePaperNote(collectionId: number, paper: PaperReference, content: string): Promise<{ content: string }> {
  return request(`/api/library/collections/${collectionId}/paper-note`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...paper, content }),
  });
}

export function createMindMap(collectionId: number, payload: {
  direction: string;
  date_from: string | null;
  date_to: string | null;
  selected_papers: PaperReference[];
}): Promise<MindMapItem> {
  return request(`/api/library/collections/${collectionId}/mind-maps`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function searchPapers(
  query: string,
  options: { limit: number; category: string; source: string },
): Promise<SearchPaper[]> {
  const params = new URLSearchParams({
    query: query.trim(),
    limit: options.limit.toString(),
    source: options.source,
  });
  if (options.category) params.set("category", options.category);
  const payload = await request<{ papers: SearchPaper[] }>(`/api/search/papers?${params}`);
  return payload.papers;
}

export function importPaper(payload: {
  source: string;
  paper_id: string;
  collection_id: number | null;
  collection_name: string | null;
}): Promise<ImportedPaper> {
  return request("/api/library/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function websocketUrl(taskId: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/${taskId}`;
}

export function register(payload: { username: string; email: string; password: string }): Promise<User> {
  return request("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function login(payload: { identifier: string; password: string }): Promise<User> {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getMe(): Promise<User> {
  return request("/api/auth/me");
}

export function logout(): Promise<void> {
  return request("/api/auth/logout", { method: "POST" });
}

export function getModelSettings(): Promise<UserModelSettings> {
  return request("/api/settings/models");
}

export function saveProvider(provider: string, payload: { api_key: string; base_url: string }): Promise<void> {
  return request(`/api/settings/providers/${provider}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function removeProviderOverride(provider: string): Promise<void> {
  return request(`/api/settings/providers/${provider}`, { method: "DELETE" });
}

export function saveAgentModel(agentRole: string, payload: { provider: string; model_name: string }): Promise<unknown> {
  return request(`/api/settings/agents/${agentRole}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function applyModelPreset(preset: string): Promise<void> {
  return request(`/api/settings/presets/${preset}`, { method: "PUT" });
}
