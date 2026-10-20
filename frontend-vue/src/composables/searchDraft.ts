import { ref, watch, type Ref } from 'vue'
import type { PaperSort, PaperSource, SearchKeyword } from '../types'

interface SearchDraft {
  query: string; keywords: SearchKeyword[]; keywordMode: 'exact' | 'fuzzy';
  source: PaperSource; sort: PaperSort; limit: number
}
type DraftRefs = { [Key in keyof SearchDraft]: Ref<SearchDraft[Key]> }
const defaults = (): SearchDraft => ({ query: '', keywords: [], keywordMode: 'fuzzy', source: 'auto', sort: 'relevance', limit: 10 })
const storageKey = (id: number) => `paperflow.search-draft.v1.${id}`

function valid(value: unknown): value is SearchDraft {
  if (!value || typeof value !== 'object') return false
  const item = value as SearchDraft
  if (typeof item.query !== 'string' || item.query.length > 500 || !Array.isArray(item.keywords) || item.keywords.length > 10
    || !['exact', 'fuzzy'].includes(item.keywordMode) || !['auto', 'arxiv', 'openalex', 'crossref'].includes(item.source)
    || !['relevance', 'latest', 'citations'].includes(item.sort) || ![10, 20].includes(item.limit)) return false
  const names = new Set<string>()
  for (const keyword of item.keywords) {
    if (!keyword || typeof keyword.text !== 'string' || !keyword.text.trim() || keyword.text !== keyword.text.trim()
      || /[\u0000-\u001f]/.test(keyword.text) || !['exact', 'fuzzy'].includes(keyword.match_mode)
      || names.has(keyword.text.toLowerCase())) return false
    names.add(keyword.text.toLowerCase())
  }
  return item.keywords.map(keyword => keyword.text).join(' / ').length <= 500
    && !(item.source === 'arxiv' && item.sort === 'citations')
}

/** Save only editable search conditions, scoped to the authenticated account. */
export function useSearchDraft(owner: Ref<number | null>, state: DraftRefs) {
  const unavailable = ref(false)
  let restoring = false
  watch(owner, id => {
    restoring = true
    let saved = defaults()
    unavailable.value = false
    if (id !== null) {
      try {
        const raw = localStorage.getItem(storageKey(id))
        if (raw && raw.length <= 12000) {
          const value: unknown = JSON.parse(raw)
          if (valid(value)) saved = value
        }
      } catch { unavailable.value = true }
    }
    state.query.value = saved.query
    state.keywords.value = saved.keywords.map(keyword => ({ ...keyword }))
    state.keywordMode.value = saved.keywordMode
    state.source.value = saved.source
    state.sort.value = saved.sort
    state.limit.value = saved.limit
    restoring = false
  }, { immediate: true, flush: 'sync' })

  watch(() => ({ query: state.query.value, keywords: state.keywords.value, keywordMode: state.keywordMode.value,
    source: state.source.value, sort: state.sort.value, limit: state.limit.value }), value => {
    if (restoring || owner.value === null) return
    try { localStorage.setItem(storageKey(owner.value), JSON.stringify(value)); unavailable.value = false }
    catch { unavailable.value = true }
  }, { deep: true, flush: 'sync' })
  return { unavailable }
}
