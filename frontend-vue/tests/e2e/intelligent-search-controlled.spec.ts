import { expect, test } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs/promises'

// Real Vue/browser flow; auth, task/model/source execution, and collection storage are simulated.
test('controlled intelligent search opens grounded report and saves provider paper on desktop and mobile', async ({ page }) => {
  const output = process.env.PAPERFLOW_E2E_OUTPUT_DIR || path.resolve('.tools/intelligent-search-browser')
  await fs.mkdir(output, { recursive: true })
  const paper = { source: 'openalex', paper_id: 'W1', title: 'Multimodal emotion recognition with EEG and eye movement on SEED-IV', abstract: 'We study multimodal emotion recognition on SEED-IV using EEG and eye movement.', authors: ['Controlled Author'], categories: ['EEG'], page_url: 'https://example.org/controlled-paper', pdf_url: null, cited_by_count: 12 }
  const report = { report_type: 'search_report', topic: '多模态情绪识别 seediv seedvii', generated_at: '2026-10-24T08:00:00Z', rounds: 2, plan: { summary: '分析多模态情绪识别与指定数据集，分别检索 SEED-IV 和 SEED-VII。', concepts: ['multimodal emotion recognition', 'EEG and eye movement'], entities: [{ name: 'SEED-IV', aliases: ['seediv', 'SEED IV'] }, { name: 'SEED-VII', aliases: ['seedvii', 'SEED VII'] }], entity_relation: 'any', constraints: ['优先 EEG 与眼动融合'], queries: [{ source: 'openalex', keywords: [{ text: 'SEED-IV', match_mode: 'fuzzy' }], purpose: '检索目标数据集的多模态研究' }] }, results: [{ candidate_id: 'c1', paper, relevance: 'match', reason: '标题和摘要包含 SEED-IV、EEG 和眼动，元数据与研究问题相关。', evidence: ['multimodal emotion recognition on SEED-IV'], matched_entities: ['SEED-IV'], modality: 'multimodal', provenance: [{ source: 'openalex', query: 'SEED-IV multimodal emotion recognition' }] }], searches: [{ round: 1, source: 'openalex', query: 'SEED-IV multimodal emotion recognition', count: 1, status: 'ok' }, { round: 2, source: 'arxiv', query: 'SEED-VII EEG eye movement', count: 0, status: 'rate_limited' }], warnings: ['arXiv 暂时限流，已保留其他来源的结果。'], gaps: ['SEED-VII 的多模态证据仍不足，建议阅读全文核实。'] }
  const task = { task_id: 'controlled-search-1', task_type: 'search', topic: report.topic, status: 'completed', created_at: report.generated_at, updated_at: report.generated_at, events: [{ stage: 'search', status: 'completed', paper_id: null, message: '完成两轮检索', timestamp: report.generated_at }], report, error_code: null, error_message: null, sync_error: null }
  let submission: any, saved: any
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const request = route.request(), url = new URL(request.url())
    let data: any
    if (url.pathname === '/api/auth/me') data = { id: 1, username: 'controlled_user', email: 'controlled@example.test', created_at: '' }
    else if (url.pathname === '/api/auth/csrf') data = { token: 'controlled-csrf', header_name: 'X-CSRF-TOKEN' }
    else if (url.pathname === '/api/library/collections') data = { collections: [{ id: 7, name: '情绪识别阅读计划', description: '', paper_count: 0 }], total: 1, page: 0, size: 100 }
    else if (url.pathname === '/api/research/tasks' && request.method() === 'POST') { submission = request.postDataJSON(); data = { ...task, status: 'queued', report: null } }
    else if (url.pathname === '/api/research/tasks/controlled-search-1') data = task
    else if (url.pathname === '/api/library/collections/7/papers') { saved = request.postDataJSON(); data = { ...paper, id: 1, added_at: '', note: '' } }
    else throw new Error(`Unexpected controlled boundary: ${request.method()} ${url.pathname}`)
    await route.fulfill({ json: { code: 1, data } })
  })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/papers')
  await page.locator('#intelligent-topic').fill(report.topic)
  await expect(page.locator('[data-test="intelligent-search-form"]')).toContainText('个人默认模型')
  await page.screenshot({ path: path.join(output, 'intelligent-search-form-desktop.png'), fullPage: true })
  await page.getByRole('button', { name: '开始智能搜索', exact: true }).click()
  await expect(page).toHaveURL(/\/research\/controlled-search-1$/)
  await expect(page.getByRole('heading', { name: '智能搜索 · 问题分析' })).toBeVisible()
  expect(submission).toEqual({ idempotency_key: expect.any(String), topic: report.topic, task_type: 'search', mode: 'live', rag: 'none', limit: 10 })
  await expect(page.getByText('满足任一实体', { exact: false })).toBeVisible()
  await expect(page.locator('.search-report')).toContainText('元数据相关性')
  await page.locator('#search-report-collection').selectOption('7')
  await page.locator('[data-test="save-search-result"]').click()
  await expect(page.locator('[data-test="save-search-result"]')).toHaveText('已加入此收藏夹')
  expect(saved).toEqual(paper)
  await expect(page.locator('a[href^="javascript:"]')).toHaveCount(0)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: path.join(output, 'intelligent-search-report-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.evaluate(() => window.scrollTo(0, 0))
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: path.join(output, 'intelligent-search-report-mobile.png'), fullPage: true })
  expect(errors).toEqual([])
})
