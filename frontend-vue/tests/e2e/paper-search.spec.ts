import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import path from 'node:path'

const originalTitle = 'Controlled arXiv evidence paper'
const password = 'Search-study-password-123!'
const output = process.env.PAPERFLOW_E2E_OUTPUT_DIR || path.resolve('../.tools/paper-search-e2e')

test('provider pagination and selected-paper Agent study reports export Word', async ({ page, browser }) => {
  const suffix = Date.now().toString(36)
  await register(page, 'study_' + suffix)
  const collection = await createCollection(page, '学习报告 ' + suffix)
  await page.goto('/papers')
  await search(page, 'paged-study', 'auto')
  await expect(page.getByRole('heading', { name: 'Controlled page 1 paper', exact: true })).toBeVisible()
  await addTo(page, collection)
  const nextResponse = page.waitForResponse(item => new URL(item.url()).pathname === '/api/papers/search')
  await page.locator('[data-test="next-page"]').click()
  const next = await nextResponse
  expect(new URL(next.url()).searchParams.get('source')).toBe('arxiv')
  expect(new URL(next.url()).searchParams.get('page')).toBe('2')
  await expect(page.getByRole('heading', { name: 'Controlled page 2 paper', exact: true })).toBeVisible()
  await addTo(page, collection)
  await page.locator('#search-source').selectOption('openalex')
  await page.locator('#search-sort').selectOption('citations')
  const cited = await search(page, 'citation-study', 'openalex')
  expect(cited.status()).toBe(200)
  await expect(page.getByText('引用 432 次', { exact: true })).toBeVisible()
  await page.goto('/collections/' + collection)
  await page.locator('[data-test="select-study-papers"]').click()
  await page.getByRole('link', { name: '生成所选论文学习报告', exact: true }).click()
  await expect(page.getByRole('checkbox')).toHaveCount(2)
  await page.getByLabel('研究主题', { exact: false }).fill('两篇论文模块学习 ' + suffix)
  await page.getByLabel('学习目标（可选）', { exact: true }).fill('理解模块输入输出')
  await page.getByRole('button', { name: '生成学习报告', exact: true }).click()
  await expect(page).toHaveURL(/\/research\/[0-9a-f-]+$/)
  const taskUrl = page.url(), taskId = taskUrl.split('/').pop()!
  const report = page.getByRole('article', { name: '论文学习报告', exact: true })
  await expect(report).toBeVisible({ timeout: 60_000 })
  await expect(report.getByRole('heading', { name: '1. 研究背景与问题', exact: true })).toHaveCount(2)
  await expect(report.getByRole('heading', { name: '2. 模型方法（模块解释）', exact: true })).toHaveCount(2)
  const downloadEvent = page.waitForEvent('download')
  await report.getByRole('link', { name: '下载 DOCX 学习报告', exact: true }).click()
  const download = await downloadEvent
  await download.saveAs(path.join(output, 'study-multi.docx'))
  expect(await download.failure()).toBeNull()
  await capture(page, 'study-report-desktop.png')
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow(page)
  await capture(page, 'study-report-mobile.png')
  await page.setViewportSize({ width: 1440, height: 1080 })
  const foreignContext = await browser.newContext({ baseURL: new URL(page.url()).origin })
  try {
    const foreign = await foreignContext.newPage()
    await register(foreign, 'study_other_' + suffix)
    expect((await foreign.request.get(`/api/research/tasks/${taskId}/document`)).status()).toBe(404)
  } finally { await foreignContext.close() }
  await page.goto('/collections/' + collection)
  await page.getByRole('link', { name: '生成单篇学习报告', exact: true }).first().click()
  await expect(page.locator('input[type=checkbox]:checked')).toHaveCount(1)
  await page.getByLabel('研究主题', { exact: false }).fill('单篇学习 ' + suffix)
  await page.getByRole('button', { name: '生成学习报告', exact: true }).click()
  await expect(page.getByRole('article', { name: '论文学习报告', exact: true })).toBeVisible({ timeout: 60_000 })
  const singleDownload = page.waitForEvent('download')
  await page.getByRole('link', { name: '下载 DOCX 学习报告', exact: true }).click()
  await (await singleDownload).saveAs(path.join(output, 'study-single.docx'))
  const saved = (await paper(page, collection)).papers[0]
  const csrf = (await (await page.request.get('/api/auth/csrf')).json()).data
  expect((await page.request.put(`/api/library/collections/${collection}/papers/${saved.id}`, {
    headers: { [csrf.header_name]: csrf.token }, data: { ...saved, title: 'missing-pdf controlled paper' },
  })).status()).toBe(200)
  await page.goto(`/research/new?task_type=study_report&collection_id=${collection}&paper_ids=${saved.id}`)
  await expect(page.locator('input[type=checkbox]:checked')).toHaveCount(1)
  await page.getByLabel('研究主题', { exact: false }).fill('验证正文失败提示 ' + suffix)
  await page.getByRole('button', { name: '生成学习报告', exact: true }).click()
  await expect(page).toHaveURL(/\/research\/[0-9a-f-]+$/)
  await expect(page.getByRole('alert')).toContainText('missing-pdf controlled paper', { timeout: 60_000 })
  await expect(page.getByRole('alert')).toContainText('PDF')
  await expect(page.getByRole('link', { name: '下载 DOCX 学习报告', exact: true })).toHaveCount(0)
  expect((await page.request.get(`/api/research/tasks/${page.url().split('/').pop()}/document`)).status()).toBe(409)
})

async function register(page: Page, username: string) {
  await page.goto('/login')
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('邮箱', { exact: true }).fill(username + '@example.test')
  await page.getByLabel(/^密码/).fill(password)
  await page.getByRole('button', { name: '注册并进入工作台' }).click()
  await expect(page).toHaveURL(/\/collections$/)
}

async function createCollection(page: Page, name: string) {
  await page.getByLabel('收藏夹名称', { exact: false }).fill(name)
  await page.getByRole('button', { name: '创建收藏夹', exact: true }).click()
  const link = page.getByRole('link', { name, exact: true })
  await expect(link).toBeVisible()
  await expect(page.getByLabel('收藏夹名称')).toHaveValue('')
  return Number((await link.getAttribute('href'))!.split('/').pop())
}

async function search(page: Page, query: string, source: string) {
  const clear = page.locator('[data-test="clear-keywords"]')
  if (await clear.isEnabled()) await clear.click()
  await page.getByLabel('检索关键词', { exact: true }).fill(query)
  await page.getByRole('combobox', { name: '文献来源', exact: true }).selectOption(source)
  const response = page.waitForResponse(item => new URL(item.url()).pathname === '/api/papers/search')
  await page.getByRole('button', { name: '搜索论文', exact: true }).click()
  return await response
}

test('mixed keyword modes, removal and Crossref citation fallback preserve explicit conditions', async ({ page }) => {
  await register(page, 'keywords_' + Date.now().toString(36))
  const collection = await createCollection(page, '关键词与引用检索')
  await page.goto('/papers')
  await page.locator('#keyword-mode').selectOption('exact')
  await page.locator('#paper-query').fill('multimodal learning')
  await page.locator('#paper-query').press('Enter')
  await page.locator('#keyword-mode').selectOption('fuzzy')
  await page.locator('#paper-query').fill('keywordpages')
  await page.locator('[data-test="add-keyword"]').click()
  await expect(page.locator('[data-test="keyword-chip"]')).toHaveCount(2)
  await page.goto('/collections')
  await page.goto('/papers')
  await expect(page.locator('[data-test="keyword-chip"]')).toHaveCount(2)
  await expect(page.locator('[data-test="keyword-chip"]').first()).toContainText('精准匹配')
  await expect(page.locator('[data-test="keyword-chip"]').last()).toContainText('模糊匹配')
  await page.reload()
  await expect(page.locator('[data-test="keyword-chip"]')).toHaveCount(2)
  await noOverflow(page)
  await capture(page, 'keyword-list-desktop.png')
  await page.setViewportSize({ width: 390, height: 844 }); await noOverflow(page)
  await capture(page, 'keyword-list-mobile.png')
  await page.setViewportSize({ width: 1440, height: 1080 })
  await page.getByRole('button', { name: '移除关键词：multimodal learning', exact: true }).click()
  await expect(page.locator('[data-test="keyword-chip"]')).toHaveCount(1)
  const responseEvent = page.waitForResponse(item => new URL(item.url()).pathname === '/api/papers/search')
  await page.getByRole('button', { name: '搜索论文', exact: true }).click()
  const data = (await (await responseEvent).json()).data
  expect(data.keywords).toEqual([{ text: 'keywordpages', match_mode: 'fuzzy' }])
  const nextEvent = page.waitForResponse(item => new URL(item.url()).pathname === '/api/papers/search')
  await page.locator('[data-test="next-page"]').click()
  const next = await nextEvent
  expect(JSON.parse(new URL(next.url()).searchParams.get('keywords')!)).toEqual(data.keywords)
  expect(new URL(next.url()).searchParams.get('source')).toBe('arxiv')
  await page.locator('#search-sort').selectOption('citations')
  const crossref = await search(page, 'citationfallback', 'auto')
  expect(crossref.status()).toBe(200)
  expect((await crossref.json()).data.used_source).toBe('crossref')
  await page.locator('#search-sort').selectOption('relevance')
  const defaultFallback = await search(page, 'citationfallback', 'auto')
  expect(defaultFallback.status()).toBe(200)
  expect((await defaultFallback.json()).data.used_source).toBe('crossref')
  await expect(page.getByRole('heading', { name: 'Controlled Crossref citation paper', exact: true })).toBeVisible()
  await expect(page.getByText('引用 987 次', { exact: true })).toBeVisible()
  await addTo(page, collection)
  expect((await paper(page, collection)).papers[0].source).toBe('crossref')
  await page.locator('[data-test="clear-keywords"]').click()
  await expect(page.locator('[data-test="keyword-chip"]')).toHaveCount(0)
  await page.reload()
  await expect(page.locator('[data-test="keyword-chip"]')).toHaveCount(0)
  await page.locator('#search-source').selectOption('crossref')
  await page.locator('#keyword-mode').selectOption('exact')
  await page.locator('#paper-query').fill('multimodal learning')
  await page.getByRole('button', { name: '搜索论文', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Crossref')
  const longText = '中'.repeat(500)
  const longSearch = await page.request.get(`/api/papers/search?${new URLSearchParams({
    source: 'arxiv', page: '1', keywords: JSON.stringify([{ text: longText, match_mode: 'fuzzy' }]),
  })}`)
  expect(longSearch.status()).toBe(200)
  expect((await longSearch.json()).data.query).toBe(longText)
})

async function addTo(page: Page, collection: number) {
  await page.getByRole('combobox', { name: '目标收藏夹', exact: true }).selectOption(String(collection))
  await page.getByRole('button', { name: '加入收藏夹', exact: true }).click()
  await expect(page.getByRole('button', { name: '已加入此收藏夹', exact: true })).toBeDisabled()
}

async function paper(page: Page, collection: number, record?: number) {
  const response = await page.request.get(`/api/library/collections/${collection}${record ? '/papers/' + record : ''}`)
  expect(response.status()).toBe(200)
  return (await response.json()).data
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
}

async function capture(page: Page, filename: string) {
  await page.evaluate(async () => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    window.scrollTo(0, 0)
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  })
  await page.screenshot({ path: path.join(output, filename), fullPage: true })
}

test('controlled provider HTTP search, personal paper edits and new research preserve collection boundaries', async ({ page, browser }) => {
  test.setTimeout(120_000)
  page.setDefaultTimeout(15_000)
  const suffix = Date.now().toString(36)
  const editedTitle = 'Personal corrected evidence paper ' + suffix
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await register(page, 'search_a_' + suffix)
  const first = await createCollection(page, '个人编辑 ' + suffix)
  const second = await createCollection(page, '原始证据 ' + suffix)
  await page.getByRole('link', { name: '搜索论文', exact: true }).click()
  await expect(page).toHaveURL(/\/papers$/)
  await search(page, 'browsersearch', 'arxiv')
  await expect(page.getByRole('heading', { name: originalTitle, exact: true })).toBeVisible()
  await page.getByText('阅读摘要与论文资料', { exact: true }).click()
  await expect(page.getByText('Controlled HTTP integration evidence', { exact: false })).toBeVisible()
  await addTo(page, first)
  await addTo(page, second)
  await noOverflow(page)
  await capture(page, 'paper-search-desktop.png')
  await page.setViewportSize({ width: 390, height: 844 })
  await noOverflow(page)
  await capture(page, 'paper-search-mobile.png')
  await page.setViewportSize({ width: 1440, height: 1080 })

  await search(page, 'browsersearch openalex', 'openalex')
  await expect(page.getByRole('heading', { name: 'Controlled OpenAlex evidence paper', exact: true })).toBeVisible()
  await search(page, 'no-result', 'openalex')
  await expect(page.getByRole('heading', { name: '没有找到匹配的论文', exact: true })).toBeVisible()
  expect((await search(page, 'source-error', 'arxiv')).status()).toBe(502)
  await expect(page.getByRole('alert')).toContainText('不可用')
  await search(page, 'fallback', 'auto')
  await expect(page.getByRole('heading', { name: 'Controlled OpenAlex evidence paper', exact: true })).toBeVisible()
  await expect(page.getByText('实际来源 openalex', { exact: false })).toBeVisible()

  await page.goto('/collections/' + first)
  await expect(page.getByRole('heading', { name: originalTitle, exact: true })).toBeVisible()
  await page.getByLabel('个人阅读笔记', { exact: true }).fill('保留个人笔记与作者姓名中的逗号。')
  await page.getByRole('button', { name: '保存论文笔记', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('论文笔记已保存')
  await page.getByRole('button', { name: '编辑论文资料', exact: true }).click()
  await expect(page.locator('#edit-paper-source')).toHaveAttribute('readonly', '')
  await expect(page.locator('#edit-paper-id')).toHaveValue('2601.00001')
  await expect(page.locator('#edit-paper-authors')).toHaveValue('Smith, John\n陈研究员')
  await page.getByLabel('标题', { exact: true }).fill(editedTitle)
  await page.locator('#edit-paper-abstract').fill('Personal corrected abstract: auditable evidence supports retrieval and research synthesis.')
  await page.getByRole('button', { name: '保存个人资料', exact: true }).click()
  await expect(page.getByRole('heading', { name: editedTitle, exact: true })).toBeVisible()
  await expect(page.getByText('本收藏夹个人编辑', { exact: true })).toBeVisible()
  const firstDetail = await paper(page, first)
  const record = firstDetail.papers[0].id as number
  expect(firstDetail.papers[0].authors).toEqual(['Smith, John', '陈研究员'])
  expect(firstDetail.papers[0].note).toContain('保留个人笔记')
  expect((await paper(page, second, record)).title).toBe(originalTitle)

  // A fresh visit resets only the browser's "added" display; a real repeated
  // POST must preserve personal metadata and notes already in the database.
  await page.goto('/papers')
  await search(page, 'browsersearch duplicate', 'arxiv')
  await expect(page.getByRole('heading', { name: originalTitle, exact: true })).toBeVisible()
  await addTo(page, first)
  const replayed = await paper(page, first, record)
  expect(replayed.title).toBe(editedTitle)
  expect(replayed.note).toContain('保留个人笔记')
  expect(replayed.metadata_edited).toBe(true)
  await page.goto('/collections/' + first)
  await page.getByRole('link', { name: '基于收藏夹发起研究', exact: true }).click()
  await page.getByLabel('研究主题').fill('使用个人修订证据 ' + suffix)
  await expect(page.getByRole('checkbox', { name: new RegExp(editedTitle) })).toBeChecked()
  await page.getByRole('button', { name: '开始研究', exact: true }).click()
  await expect(page.getByRole('heading', { name: '研究完成', exact: true })).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('article', { name: '研究报告', exact: true }).getByRole('heading', { name: editedTitle, exact: true })).toBeVisible()

  const otherContext = await browser.newContext({ baseURL: new URL(page.url()).origin })
  const other = await otherContext.newPage()
  try {
    await register(other, 'search_b_' + suffix)
    const bCollection = await createCollection(other, '另一位用户 ' + suffix)
    await other.goto('/papers')
    await search(other, 'browsersearch other-user', 'arxiv')
    await expect(other.getByRole('heading', { name: originalTitle, exact: true })).toBeVisible()
    await addTo(other, bCollection)
    expect((await paper(other, bCollection, record)).title).toBe(originalTitle)
    expect((await other.request.get(`/api/library/collections/${first}/papers/${record}`)).status()).toBe(404)
    const csrf = (await (await other.request.get('/api/auth/csrf')).json()).data
    const forbidden = await other.request.put(`/api/library/collections/${first}/papers/${record}`, {
      headers: { [csrf.header_name]: csrf.token }, data: { ...replayed, title: 'Forbidden overwrite' },
    })
    expect(forbidden.status()).toBe(404)
  } finally {
    await otherContext.close()
  }
  await page.goto('/collections/' + first)
  await expect(page.getByRole('heading', { name: editedTitle, exact: true })).toBeVisible()
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '移除论文：' + editedTitle, exact: true }).click()
  await expect(page.getByRole('heading', { name: '还没有论文', exact: true })).toBeVisible()
  expect((await paper(page, second, record)).title).toBe(originalTitle)
  expect(errors).toEqual([])
})
