import { chromium } from "playwright";
import fs from "node:fs/promises";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const marker = "CUA-E2E-ORDER-SELECT-20260731";
const results = [];
const record = (id, passed, actual) => results.push({ id, status: passed ? "PASS" : "FAIL", actual });

async function waitDone() {
  await page.waitForFunction(() => !document.querySelector(".widget-form button")?.hasAttribute("disabled"), null, { timeout: 120_000 });
}

try {
  await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
  await page.locator('input[name="email"]').fill("user1@test.com");
  await page.locator('input[name="password"]').fill("user");
  await page.locator("form button").click();
  await page.waitForURL(/\/portal/, { timeout: 15_000 });
  await page.locator(".chat-launcher").click();
  await page.locator('.widget-head button[title]').first().click();
  await page.locator(".conversation-history .new-chat").click();

  await page.locator(".widget-form input").fill(`${marker} Kiểm tra các đơn hiện có của tôi đang ở đâu`);
  await page.locator(".widget-form button").click();
  await page.waitForSelector(".agent-ui-options button", { timeout: 120_000 });
  await waitDone();

  const options = page.locator(".agent-ui-options button");
  const optionCount = await options.count();
  const firstOrder = (await options.first().innerText()).match(/ORD-[A-Z0-9]+/)?.[0] || "";
  record("ORDER-SELECTOR-RENDER", optionCount > 0 && Boolean(firstOrder), { optionCount, firstOrder });
  record("ORDER-SELECTOR-ENABLED", !(await options.first().isDisabled()), await options.first().innerText());

  const agentCount = await page.locator(".message.agent").count();
  await options.first().click();
  await page.waitForFunction((count) => document.querySelectorAll(".message.agent").length > count, agentCount, { timeout: 120_000 });
  await waitDone();
  const selectedAnswer = await page.locator(".message.agent").last().innerText();
  record("ORDER-SELECTOR-CONTINUE", selectedAnswer.includes(firstOrder), selectedAnswer);
  record("ORDER-SELECTOR-NO-ERROR", !/UNSUPPORTED_INTERACTION|INVALID_INTERACTION|hết hạn/i.test(selectedAnswer), selectedAnswer);

  await page.locator('.widget-head button[title]').first().click();
  await page.locator(".conversation-history .new-chat").click();
  const brandBefore = await page.locator(".message.agent").count();
  await page.locator(".widget-form input").fill("CUA-E2E-BRAND-20260731 OmniVIP là gì và điều kiện trả hàng thế nào?");
  await page.locator(".widget-form button").click();
  await page.waitForFunction((count) => document.querySelectorAll(".message.agent").length > count, brandBefore, { timeout: 120_000 });
  await waitDone();
  const brandedAnswer = await page.locator(".message.agent").last().innerText();
  record("BRAND-OMNI", /Omni/i.test(brandedAnswer) && !/Shopee/i.test(brandedAnswer), brandedAnswer);

  await page.locator('.widget-head button[title]').first().click();
  await page.locator(".conversation-history .new-chat").click();
  await page.locator(".widget-form input").fill("CUA-E2E-CANCEL-SELECT-20260731 Tôi muốn hủy một đơn hàng");
  await page.locator(".widget-form button").click();
  await page.waitForSelector(".agent-ui-options button", { timeout: 120_000 });
  await waitDone();
  const cancelOptions = page.locator(".agent-ui-options button");
  const cancelOrder = (await cancelOptions.first().innerText()).match(/ORD-[A-Z0-9]+/)?.[0] || "";
  const cancelBefore = await page.locator(".message.agent").count();
  await cancelOptions.first().click();
  await page.waitForFunction((count) => document.querySelectorAll(".message.agent").length > count, cancelBefore, { timeout: 120_000 });
  await waitDone();
  const confirmation = page.locator(".message.agent").last();
  record("CANCEL-SELECTOR-CONTINUE", Boolean(cancelOrder) && (await confirmation.innerText()).includes(cancelOrder) && await confirmation.locator(".agent-ui-card").count() === 1, await confirmation.innerText());

  await page.screenshot({ path: "E:/Code _Project/ChatAgent/output/playwright/order-selection-regression.png", fullPage: true });
} catch (error) {
  results.push({ id: "SUITE", status: "FAIL", actual: error.stack || error.message });
}

const report = { generatedAt: new Date().toISOString(), marker, passed: results.filter((item) => item.status === "PASS").length, failed: results.filter((item) => item.status === "FAIL").length, results };
await fs.writeFile("E:/Code _Project/ChatAgent/output/playwright/order-selection-regression.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
await browser.close();
