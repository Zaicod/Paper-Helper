import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import path from 'node:path'
import { randomUUID } from 'node:crypto'

const output = process.env.PAPERFLOW_E2E_OUTPUT_DIR || path.resolve('../.tools/model-settings-e2e')
// Deliberately fake values. The test fixture checks these at the model boundary.
const keys = { qwen: 'fixture-personal-qwen-1234', openai: 'fixture-personal-openai-5678' }
type Provider = keyof typeof keys

async function register(page: Page, username: string) {
  await page.goto('/login')
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('邮箱', { exact: true }).fill(username + '@example.test')
  await page.getByLabel(/^密码/).fill('Model-settings-password-123!')
  await page.getByRole('button', { name: '注册并进入工作台' }).click()
  await expect(page).toHaveURL(/\/collections$/)
}

async function savedSettings(page: Page) {
  const response = await page.request.get('/api/model-settings')
  expect(response.status()).toBe(200)
  const text = await response.text()
  for (const key of Object.values(keys)) expect(text).not.toContain(key)
  return JSON.parse(text).data
}

async function save(page: Page, provider: Provider, model: string, key?: string) {
  await page.locator(`[data-test="${provider}-model"]`).fill(model)
  if (key) await page.locator(`[data-test="${provider}-key"]`).fill(key)
  const response = page.waitForResponse(r => new URL(r.url()).pathname === `/api/model-settings/${provider}` && r.request().method() === 'PUT')
  await page.locator(`[data-test="${provider}-save"]`).click()
  expect((await response).status()).toBe(200)
  await expect(page.locator(`[data-test="${provider}-key"]`)).toHaveValue('')
}

test('saved personal models stay masked and reach actual Java-to-worker study dispatch', async ({ page, browser }) => {
  const suffix = Date.now().toString(36)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await register(page, 'models_' + suffix)
  await page.getByRole('link', { name: '个人设置', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: '个人设置', exact: true })).toBeVisible()
  await expect(page.locator('.account-summary')).toContainText('models_' + suffix)
  await expect(page.getByRole('link', { name: '打开个人设置', exact: true })).toHaveAttribute('href', '/settings')
  for (const provider of ['qwen', 'openai'] as Provider[]) {
    await expect(page.locator(`[data-test="${provider}-key"]`)).toHaveAttribute('type', 'password')
    await save(page, provider, `fixture-${provider}-model`, keys[provider])
  }
  await page.reload()
  for (const provider of ['qwen', 'openai'] as Provider[]) {
    await expect(page.locator(`[data-test="${provider}-key"]`)).toHaveValue('')
    await expect(page.locator(`[data-test="${provider}-model"]`)).toHaveValue(`fixture-${provider}-model`)
    await expect(page.locator(`[data-test="${provider}-card"]`)).toContainText(keys[provider].slice(-4))
    // Blank input keeps the old key; the saved connection test must still pass.
    await save(page, provider, `fixture-${provider}-updated`)
    const response = page.waitForResponse(r => new URL(r.url()).pathname === `/api/model-settings/${provider}/test`)
    await page.locator(`[data-test="${provider}-test"]`).click()
    const tested = await response
    expect(tested.status()).toBe(200)
    expect((await tested.json()).data.success).toBe(true)
  }
  const qwenDefault = page.waitForResponse(r => new URL(r.url()).pathname === '/api/model-settings/default' && r.request().method() === 'PUT')
  await page.locator('[data-test="default-model-provider"]').selectOption('qwen')
  await page.getByRole('button', { name: '保存默认选择', exact: true }).click()
  expect((await qwenDefault).status()).toBe(200)
  expect((await savedSettings(page)).default_provider).toBe('qwen')
  const defaultResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/model-settings/default' && r.request().method() === 'PUT')
  await page.locator('[data-test="default-model-provider"]').selectOption('openai')
  await page.getByRole('button', { name: '保存默认选择', exact: true }).click()
  expect((await defaultResponse).status()).toBe(200)
  expect((await savedSettings(page)).default_provider).toBe('openai')
  await page.reload()
  await expect(page.locator('[data-test="openai-card"]')).toContainText('当前默认')
  await expect(page.locator('[data-test="current-model"]')).toContainText('fixture-openai-updated')
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage }))).not.toContain(keys.openai)
  expect(await page.evaluate(() => JSON.stringify({ ...sessionStorage }))).not.toContain(keys.qwen)
  await page.screenshot({ path: path.join(output, 'model-settings-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
  await page.screenshot({ path: path.join(output, 'model-settings-mobile.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1080 })

  // Seed ordinary application data over its real authenticated API.
  const csrf = (await (await page.request.get('/api/auth/csrf')).json()).data
  const headers = { [csrf.header_name]: csrf.token }
  const created = await page.request.post('/api/library/collections', { headers, data: { name: '模型设置学习 ' + suffix, description: '' } })
  expect(created.status()).toBe(201)
  const collection = (await created.json()).data.id
  const added = await page.request.post(`/api/library/collections/${collection}/papers`, { headers, data: {
    source: 'manual', paper_id: 'models-study-' + suffix, title: 'Controlled personal model study',
    abstract: 'Controlled evidence for personal model dispatch integration.', authors: ['Fixture Researcher'],
    categories: ['cs.AI'], page_url: 'https://example.test/personal-study', pdf_url: 'https://example.test/personal-study.pdf',
  } })
  expect(added.status()).toBe(201)
  await page.goto(`/research/new?task_type=study_report&collection_id=${collection}`)
  await page.getByText('研究设置', { exact: true }).click()
  await expect(page.locator('[data-test="task-provider"]')).toHaveValue('openai')
  await expect(page.locator('[data-test="task-model"]')).toHaveValue('fixture-openai-updated')
  await expect(page.locator('input[type=checkbox]:checked')).toHaveCount(1)
  await page.getByLabel('研究主题', { exact: false }).fill('验证个人默认模型 ' + suffix)
  await page.getByRole('button', { name: '生成学习报告', exact: true }).click()
  await expect(page).toHaveURL(/\/research\/[0-9a-f-]+$/)
  await expect(page.getByRole('article', { name: '论文学习报告', exact: true })).toBeVisible({ timeout: 60_000 })
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('link', { name: '下载 DOCX 学习报告', exact: true }).click()
  const download = await downloadEvent
  await download.saveAs(path.join(output, 'personal-model-study.docx'))
  expect(await download.failure()).toBeNull()
  await page.reload()
  await expect(page.getByRole('article', { name: '论文学习报告', exact: true })).toBeVisible()

  const otherContext = await browser.newContext({ baseURL: new URL(page.url()).origin })
  try {
    const other = await otherContext.newPage()
    await register(other, 'models_other_' + suffix)
    const empty = await savedSettings(other)
    expect(empty.default_provider).toBeNull()
    expect(empty.providers.every((item: { configured: boolean }) => !item.configured)).toBe(true)
    await other.goto('/model-settings')
    await save(other, 'qwen', 'fixture-qwen-other', 'fixture-personal-qwen-other-9999')
    const otherTest = other.waitForResponse(r => new URL(r.url()).pathname === '/api/model-settings/qwen/test')
    await other.locator('[data-test="qwen-test"]').click()
    expect((await (await otherTest).json()).data.success).toBe(true)
    expect((await savedSettings(page)).providers.find((item: { provider: string }) => item.provider === 'qwen').model).toBe('fixture-qwen-updated')
  } finally { await otherContext.close() }

  await page.goto('/model-settings')
  const ownTest = page.waitForResponse(r => new URL(r.url()).pathname === '/api/model-settings/qwen/test')
  await page.locator('[data-test="qwen-test"]').click()
  expect((await (await ownTest).json()).data.success).toBe(true)
  await page.locator('[data-test="openai-delete"]').click()
  const deleted = page.waitForResponse(r => new URL(r.url()).pathname === '/api/model-settings/openai/key' && r.request().method() === 'DELETE')
  await page.locator('[data-test="openai-confirm-delete"]').click()
  expect((await deleted).status()).toBe(200)
  const settings = await savedSettings(page)
  expect(settings.default_provider).toBe('openai')
  expect(settings.providers.find((item: { provider: string }) => item.provider === 'openai').configured).toBe(false)
  // An omitted provider still resolves the explicit personal marker after deletion.
  const refused = await page.request.post('/api/research/tasks', { headers, data: {
    task_type: 'study_report', topic: '删除密钥后不能回退', mode: 'live', rag: 'abstract', limit: 1,
    collection_id: collection, paper_ids: [(await added.json()).data.id], idempotency_key: randomUUID(),
  } })
  expect(refused.status()).toBe(202)
  if ([200, 202].includes(refused.status())) {
    const taskId = (await refused.json()).data.task_id
    await page.goto('/research/' + taskId)
    await expect(page.getByRole('alert')).toContainText(/模型|密钥|配置/, { timeout: 60_000 })
    // Recover from a failed personal model configuration without reselecting papers.
    const original = (await (await page.request.get('/api/research/tasks/' + taskId)).json()).data
    await expect(page.getByRole('button', { name: '重试任务', exact: true })).toBeVisible()
    await page.goto('/settings')
    await page.locator('[data-test="default-model-provider"]').selectOption('qwen')
    const changed = page.waitForResponse(r => new URL(r.url()).pathname === '/api/model-settings/default' && r.request().method() === 'PUT')
    await page.getByRole('button', { name: '保存默认选择', exact: true }).click()
    expect((await changed).status()).toBe(200)
    await page.goto('/research/' + taskId)
    const retried = page.waitForResponse(r => new URL(r.url()).pathname === `/api/research/tasks/${taskId}/retry`)
    await page.getByRole('button', { name: '重试任务', exact: true }).click()
    const newResponse = await retried
    expect(newResponse.status()).toBe(202)
    const newId = (await newResponse.json()).data.task_id
    expect(newId).not.toBe(taskId)
    await expect(page).toHaveURL(new RegExp('/research/' + newId + '$'))
    await expect(page.getByRole('article', { name: '论文学习报告', exact: true })).toBeVisible({ timeout: 60_000 })
    const old = (await (await page.request.get('/api/research/tasks/' + taskId)).json()).data
    expect(old.status).toBe('failed')
    expect(old.updated_at).toBe(original.updated_at)
    expect(old.error_message).toBe(original.error_message)
    const snapshot = (await (await page.request.get('/api/research/tasks/' + newId)).json()).data
    expect(snapshot.topic).toBe(original.topic)
    expect(snapshot.report.papers[0].paper_id).toBe('models-study-' + suffix)
  } else {
    expect([400, 409]).toContain(refused.status())
    expect(await refused.text()).toMatch(/模型|密钥|配置/)
  }
  expect(errors).toEqual([])
})

