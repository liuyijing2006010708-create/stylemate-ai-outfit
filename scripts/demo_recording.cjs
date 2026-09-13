// Isolated, key-free demo recording. Never attach to a personal browser profile.
const { chromium } = require(process.env.STYLEMATE_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const url = process.env.STYLEMATE_DEMO_URL || 'http://127.0.0.1:8504';
  const output = path.resolve('outputs/p0-1-demo');
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      recordVideo: { dir: output, size: { width: 1440, height: 1000 } },
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.getByText('版本 0.2.0-rc.1', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, '01-api.png') });
    // Pauses intentionally make the recording readable, not synchronization.
    await page.waitForTimeout(2500);
    await page.getByRole('button', { name: '暂不配置，仅查看固定 Demo', exact: true }).click();
    await page.getByRole('button', { name: '✦ 查看固定 Demo', exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, '02-input.png') });
    await page.waitForTimeout(2500);
    await page.getByRole('button', { name: '✦ 查看固定 Demo', exact: true }).click();
    await page.getByRole('heading', { name: '为你生成的 3 套穿搭' }).waitFor();
    await page.screenshot({ path: path.join(output, '03-results.png'), fullPage: true });
    await page.waitForTimeout(3500);
    const save = page.getByRole('button', { name: '收藏', exact: true }).first();
    await save.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);
    await save.click();
    const collection = page.getByText('我的收藏（本会话 · 1 套）', { exact: true });
    await collection.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2500);
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: '下载效果图', exact: true }).first().click();
    const file = await download;
    assert(file.suggestedFilename().endsWith('.png'));
    await file.saveAs(path.join(output, 'demo-export.png'));
    assert.deepEqual(errors, []);
    const video = page.video();
    await context.close();
    await video.saveAs(path.join(output, 'stylemate-fixed-demo.webm'));
    console.log('PASS: fixed Demo, three outfits, collection, PNG export; no API requests.');
    console.log(path.join(output, 'stylemate-fixed-demo.webm'));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exit(1); });
