import { chromium } from "playwright";
import fs from "node:fs/promises";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const results = [];
const record = (id, passed, actual) => results.push({ id, status: passed ? "PASS" : "FAIL", actual });

async function login(email, password) {
  await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator("form button").click();
}

try {
  await login("admin@test.com", "admin");
  await page.waitForURL(/\/admin/, { timeout: 15_000 });
  record("AUTH-ADMIN", true, page.url());

  await page.goto("http://localhost:3000/admin/graph", { waitUntil: "networkidle" });
  await page.waitForSelector(".knowledge-node", { timeout: 15_000 });
  const graphNodes = await page.locator(".knowledge-node").count();
  const graphStatus = await page.locator(".graph-commandbar span").innerText();
  record("GRAPH-PUBLISHED-PREVIEW", graphNodes > 0 && graphStatus.includes("Published Graph"), { graphNodes, graphStatus });
  await page.screenshot({ path: "E:/Code _Project/ChatAgent/output/playwright/graph-published.png", fullPage: true });

  await page.context().clearCookies();
  await login("user1@test.com", "user");
  await page.waitForURL(/\/portal/, { timeout: 15_000 });
  record("AUTH-USER", true, page.url());

  await page.locator(".chat-launcher").click();
  const before = await page.locator(".message.agent").count();
  await page.locator(".widget-form input").fill("CUA-E2E-20260731 Điều kiện trả hàng và bằng chứng cần có là gì?");
  await page.locator(".widget-form button").click();
  await page.waitForFunction((count) => document.querySelectorAll(".message.agent").length > count, before, { timeout: 120_000 });
  await page.waitForFunction(() => !document.querySelector(".widget-form button")?.hasAttribute("disabled"), null, { timeout: 120_000 });
  const latest = page.locator(".message.agent").last();
  const answer = await latest.innerText();
  const citations = await latest.locator(".citation").count();
  record("CHAT-STREAM-DONE", answer.length > 80, answer);
  record("CHAT-CITATIONS", citations > 0, citations);
  await page.screenshot({ path: "E:/Code _Project/ChatAgent/output/playwright/chat-regression.png", fullPage: true });
} catch (error) {
  results.push({ id: "SUITE", status: "FAIL", actual: error.stack || error.message });
}

const report = { generatedAt: new Date().toISOString(), passed: results.filter((item) => item.status === "PASS").length, failed: results.filter((item) => item.status === "FAIL").length, results };
await fs.writeFile("E:/Code _Project/ChatAgent/output/playwright/regression.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
await browser.close();
