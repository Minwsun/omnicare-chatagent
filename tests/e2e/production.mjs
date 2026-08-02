import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";

const base = process.env.WEB_BASE_URL || "https://omnicare-chatagent.vercel.app";
const output = process.env.E2E_OUTPUT || "output/playwright/production-release.json";
const browser = await chromium.launch({ headless: true });
const results = [];
const errors = [];
const record = (id, passed, actual) => results.push({ id, status: passed ? "PASS" : "FAIL", actual });

async function login(page, email, password, route) {
  await page.goto(`${base}/login`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  const loginResponse = page.waitForResponse(response => response.url().includes("/api/auth/login") && response.request().method() === "POST", { timeout: 30_000 });
  await page.locator("form button").click();
  const response = await loginResponse;
  if (!response.ok()) throw new Error(`LOGIN_FAILED_${response.status()}: ${await response.text()}`);
  await page.waitForURL(new RegExp(`${route}(?:$|/)`), { timeout: 60_000 });
}

async function testCustomer() {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  page.on("console", message => { if (message.type() === "error") errors.push({ surface: "customer", message: message.text() }); });
  await login(page, "user1@test.com", "user", "/portal");
  record("AUTH-CUSTOMER", true, page.url());
  await page.locator(".chat-launcher").click();
  record("CHAT-POPUP", await page.locator(".chat-popup").isVisible(), await page.locator(".chat-popup").count());
  const started = Date.now();
  await page.locator('.widget-form input:not([type="file"])').fill("Tôi có thể hủy đơn nào?");
  await page.locator('.widget-form button[type="submit"],.widget-form>button').last().click();
  await page.waitForFunction(() => !document.querySelector(".widget-form button")?.hasAttribute("disabled"), null, { timeout: 120_000 });
  const latencyMs = Date.now() - started;
  const agentMessages = await page.locator(".message.agent").count();
  const selectors = await page.locator(".agent-ui-card,.order-choices").count();
  record("CHAT-ANSWER", agentMessages > 0, { agentMessages, latencyMs });
  record("ORDER-SELECTION", selectors > 0, selectors);
  await page.screenshot({ path: "output/playwright/production-customer.png", fullPage: true });
  await context.close();
}

async function testAdmin() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on("console", message => { if (message.type() === "error") errors.push({ surface: "admin", message: message.text() }); });
  await login(page, "admin@test.com", "admin", "/admin");
  record("AUTH-ADMIN", true, page.url());
  const nav = await page.locator(".admin-sidebar").innerText();
  record("ADMIN-INBOX-NAV", nav.includes("Inbox hỗ trợ"), nav);
  await page.goto(`${base}/admin/inbox`, { waitUntil: "domcontentloaded", timeout: 60_000 });
  record("ADMIN-INBOX-PAGE", await page.locator(".ticket-queue").count() === 1, page.url());
  await page.goto(`${base}/admin/knowledge`, { waitUntil: "domcontentloaded", timeout: 60_000 });
  record("ADMIN-KB", await page.locator("body").innerText().then(text => text.includes("Knowledge") || text.includes("Tài liệu")), page.url());
  await page.screenshot({ path: "output/playwright/production-admin.png", fullPage: true });
  await context.close();
}

try {
  await testCustomer();
  await testAdmin();
} catch (error) {
  errors.push({ surface: "suite", message: error instanceof Error ? error.stack : String(error) });
}

await mkdir("output/playwright", { recursive: true });
const report = { generatedAt: new Date().toISOString(), base, passed: results.filter(item => item.status === "PASS").length, failed: results.filter(item => item.status === "FAIL").length, results, errors };
await writeFile(output, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
await browser.close();
if (report.failed || errors.some(item => item.surface === "suite")) process.exitCode = 1;
