import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import path from 'node:path'

const output = process.env.PAPERFLOW_E2E_OUTPUT_DIR || path.resolve('../.tools')
const password = 'Vue-study-password-123!'

async function register(page: Page, username: string) {
  await page.goto('/login')
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('邮箱', { exact: true }).fill(username + '@example.test')
  await page.getByLabel(/^密码/).fill(password)
  await page.getByRole('button', { name: '注册并进入工作台' }).click()
  await expect(page).toHaveURL(/\/collections$/)
}

async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow, 'The page must fit the viewport without horizontal scrolling').toBeLessThanOrEqual(1)
}

test('real account, collection, Agent report and private history work on desktop and mobile', async ({ page, browser }) => {
  const suffix = Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
  const username = 'vue_a_' + suffix
  const collectionName = '证据研究 ' + suffix
  const paperTitle = 'Auditable retrieval agents: a local integration study'
  const paperId = 'vue-evidence-' + suffix
  const topic = '可追溯的检索增强研究 ' + suffix
  const browserErrors: string[] = []
  page.on('pageerror', error => browserErrors.push(error.message))

  await register(page, username)
  await expect(page.getByRole('heading', { name: '从一个研究问题开始' })).toBeVisible()
  await page.getByLabel('收藏夹名称').fill(collectionName)
  await page.getByLabel('描述', { exact: true }).fill('三服务真实联调：研究问题、证据与笔记。')
  await page.getByRole('button', { name: '创建收藏夹', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '收藏夹已创建' })).toBeVisible()
  await page.getByRole('link', { name: collectionName, exact: true }).click()
  await expect(page).toHaveURL(/\/collections\/\d+$/)
  await expect(page.getByRole('heading', { name: collectionName, exact: true, level: 1 })).toBeVisible()
  const collectionUrl = page.url()
  await page.getByLabel('研究笔记', { exact: true }).fill('收藏夹笔记：核查证据来源和研究范围。')
  await page.getByRole('button', { name: '保存收藏夹笔记', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('收藏夹笔记已保存')

  await page.getByLabel('来源 *', { exact: true }).fill('manual')
  await page.getByLabel('来源论文 ID *', { exact: true }).fill(paperId)
  await page.getByLabel('论文标题 *', { exact: true }).fill(paperTitle)
  await page.getByLabel('摘要', { exact: true }).fill('We study retrieval augmented research agents using auditable evidence chunks. The system retrieves passages from paper abstracts, analyzes each paper and synthesizes research ideas. This abstract is manually supplied integration data, not a verified scientific result.')
  await page.getByLabel('作者', { exact: true }).fill('Alice Researcher, 陈研究员')
  await page.getByLabel('分类', { exact: true }).fill('cs.AI, cs.IR')
  await page.getByLabel('论文页面链接 *', { exact: true }).fill('https://example.test/papers/' + paperId)
  await page.getByRole('button', { name: '添加论文', exact: true }).click()
  await expect(page.getByRole('heading', { name: paperTitle, exact: true })).toBeVisible()
  await page.getByLabel('个人阅读笔记', { exact: true }).fill('论文笔记：摘要中的证据需要进一步验证。')
  await page.getByRole('button', { name: '保存论文笔记', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('论文笔记已保存')
  await page.reload()
  await expect(page.getByLabel('研究笔记', { exact: true })).toHaveValue('收藏夹笔记：核查证据来源和研究范围。')
  await expect(page.getByLabel('个人阅读笔记', { exact: true })).toHaveValue('论文笔记：摘要中的证据需要进一步验证。')
  await noHorizontalOverflow(page)

  await page.getByRole('link', { name: '基于收藏夹发起研究', exact: true }).click()
  await page.getByLabel('研究主题').fill(topic)
  await expect(page.getByRole('checkbox', { name: new RegExp(paperTitle) })).toBeChecked()
  await page.getByLabel('执行模式').selectOption('demo')
  await page.getByText('研究设置', { exact: true }).click()
  await page.getByLabel('证据检索').selectOption('abstract')
  await page.getByRole('button', { name: '开始研究', exact: true }).click()
  await expect(page).toHaveURL(/\/research\/[0-9a-f-]{36}$/)
  const taskUrl = page.url()
  await expect(page.getByRole('heading', { name: '研究完成', exact: true })).toBeVisible({ timeout: 60_000 })
  const report = page.getByRole('article', { name: '研究报告', exact: true })
  await expect(report).toBeVisible()
  await expect(report.getByRole('heading', { name: '综合理解', exact: true })).toBeVisible()
  await expect(report.getByRole('heading', { name: '证据审计', exact: true })).toBeVisible()
  await expect(report.getByText('这是离线演示想法', { exact: false })).toBeVisible()
  await expect(page.getByRole('list', { name: '研究阶段记录' }).locator('li')).toHaveCount(10)
  await report.locator('details.audit summary').click()
  await expect(report.locator('.chunk-ids')).not.toHaveText('无')
  await noHorizontalOverflow(page)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: path.join(output, 'vue-desktop.png'), fullPage: true })

  await page.reload()
  await expect(page.getByRole('heading', { name: '研究完成', exact: true })).toBeVisible()
  await expect(page.getByRole('article', { name: '研究报告', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '返回任务', exact: true }).click()
  await expect(page.getByRole('link', { name: new RegExp(topic) })).toBeVisible()
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('用户名或邮箱', { exact: true }).fill(username)
  await page.getByLabel(/^密码/).fill(password)
  await page.getByRole('button', { name: '登录工作台' }).click()
  await expect(page).toHaveURL(/\/collections$/)
  await page.goto(taskUrl)
  await expect(page.getByRole('heading', { name: '研究完成', exact: true })).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await noHorizontalOverflow(page)
  await page.goto(collectionUrl)
  await expect(page.getByRole('heading', { name: paperTitle, exact: true })).toBeVisible()
  await noHorizontalOverflow(page)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: path.join(output, 'vue-mobile.png'), fullPage: true })

  const otherContext = await browser.newContext({ baseURL: new URL(taskUrl).origin, viewport: { width: 390, height: 844 } })
  const other = await otherContext.newPage()
  try {
    await register(other, 'vue_b_' + suffix)
    await expect(other.getByRole('heading', { name: '从一个研究问题开始' })).toBeVisible()
    await expect(other.getByRole('link', { name: collectionName, exact: true })).toHaveCount(0)
    await noHorizontalOverflow(other)
    await other.goto('/research')
    await expect(other.getByRole('heading', { name: '还没有研究记录', exact: true })).toBeVisible()
    // A known UUID and collection URL must still fail ownership checks.
    await other.goto(taskUrl)
    await expect(other.getByRole('alert')).toBeVisible()
    await expect(other.getByRole('article', { name: '研究报告', exact: true })).toHaveCount(0)
    await other.goto(collectionUrl)
    await expect(other.getByRole('heading', { name: '暂时无法打开收藏夹', exact: true })).toBeVisible()
    await expect(other.getByRole('heading', { name: paperTitle, exact: true })).toHaveCount(0)
  } finally {
    await otherContext.close()
  }
  expect(browserErrors).toEqual([])
})
