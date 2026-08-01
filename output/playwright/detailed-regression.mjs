import { chromium } from "playwright";
import fs from "node:fs/promises";

const base = "http://localhost:3000";
const output = "E:/Code _Project/ChatAgent/output/playwright";
const marker = "CUA-E2E-DETAIL-20260731";
const browser = await chromium.launch({ headless: true });
const results = [];
const browserErrors = [];

const record = (id, passed, actual) => results.push({ id, status: passed ? "PASS" : "FAIL", actual });
const screenshot = async (page, name) => page.screenshot({ path: `${output}/${name}`, fullPage: true });

async function login(page, email, password) {
  await page.goto(`${base}/login`, { waitUntil: "networkidle" });
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator("form button").click();
}

async function waitForAgent(page, before) {
  await page.waitForFunction((count) => document.querySelectorAll(".message.agent").length > count, before, { timeout: 120_000 });
  await page.waitForFunction(() => !document.querySelector(".widget-form button")?.hasAttribute("disabled"), null, { timeout: 120_000 });
}

const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
page.on("console", (message) => {
  if (message.type() === "error" && !message.text().includes("401")) browserErrors.push({ url: page.url(), type: "console", text: message.text() });
});
page.on("pageerror", (error) => browserErrors.push({ url: page.url(), type: "pageerror", text: error.message }));

try {
  await login(page, "admin@test.com", "wrong-password");
  await page.waitForTimeout(400);
  record("AUTH-01-INVALID", page.url().includes("/login") && await page.locator(".form-error").count() === 1, await page.locator(".form-error").innerText());

  await login(page, "admin@test.com", "admin");
  await page.waitForURL(/\/admin/, { timeout: 15_000 });
  record("AUTH-02-ADMIN", page.url().endsWith("/admin"), page.url());

  await page.goto(`${base}/admin`, { waitUntil: "networkidle" });
  record("ADMIN-01-DASHBOARD", await page.locator(".metrics").count() > 0, (await page.locator("body").innerText()).slice(0, 500));

  await page.goto(`${base}/admin/knowledge`, { waitUntil: "networkidle" });
  const knowledgeText = await page.locator("body").innerText();
  record("ADMIN-02-KNOWLEDGE", knowledgeText.length > 300, knowledgeText.slice(0, 700));
  await screenshot(page, "detailed-admin-knowledge.png");

  await page.goto(`${base}/admin/graph`, { waitUntil: "networkidle" });
  await page.waitForSelector(".knowledge-node", { timeout: 15_000 });
  const graphNodes = await page.locator(".knowledge-node").count();
  const graphEdges = await page.locator(".react-flow__edge").count();
  const graphStatus = await page.locator(".graph-commandbar span").innerText();
  record("GRAPH-01-PUBLISHED", graphNodes > 0 && graphStatus.includes("Published Graph"), { graphNodes, graphEdges, graphStatus });
  record("GRAPH-02-READONLY", await page.locator('.graph-commandbar button:has-text("Publish")').isDisabled(), "Publish disabled in published preview");
  await screenshot(page, "detailed-graph.png");

  await context.clearCookies();
  await login(page, "user1@test.com", "user");
  await page.waitForURL(/\/portal/, { timeout: 15_000 });
  record("AUTH-03-USER", page.url().endsWith("/portal"), page.url());

  await page.goto(`${base}/portal/orders`, { waitUntil: "networkidle" });
  const orderCards = page.locator('a.data-card[href^="/portal/orders/"]');
  const orderCount = await orderCards.count();
  record("ORDER-01-LIST", orderCount > 0, { orderCount });
  const cancellableOrder = await page.evaluate(async () => {
    const response = await fetch("/api/me/orders", { cache: "no-store" });
    const data = await response.json();
    return data.orders.find((order) => ["PENDING", "CONFIRMED", "PROCESSING"].includes(order.status));
  });
  const orderHref = cancellableOrder ? `/portal/orders/${cancellableOrder.id}` : await orderCards.first().getAttribute("href");
  await page.goto(`${base}${orderHref}`, { waitUntil: "networkidle" });
  const orderText = await page.locator("body").innerText();
  const orderId = orderText.match(/ORD-[A-Z0-9]+/)?.[0] || "";
  record("ORDER-02-DETAIL", Boolean(orderId) && await page.locator(".fact-grid").count() === 1, { orderId });
  await screenshot(page, "detailed-order.png");

  await page.locator(".chat-launcher").click();
  record("CHAT-01-POPUP", await page.locator(".chat-popup").isVisible(), await page.locator(".chat-popup").innerText());

  let before = await page.locator(".message.agent").count();
  await page.locator(".widget-form input").fill(`${marker} \u0110\u01a1n n\u00e0y c\u00f3 th\u1ec3 h\u1ee7y kh\u00f4ng?`);
  await page.locator(".widget-form button").click();
  await waitForAgent(page, before);
  let latest = page.locator(".message.agent").last();
  const cancelAnswer = await latest.innerText();
  const generatedUi = await latest.locator(".agent-ui-card").count();
  record("CHAT-02-ORDER-TOOL", cancelAnswer.includes(orderId), cancelAnswer);
  record("CHAT-03-CONFIRMATION-UI", generatedUi > 0, { generatedUi });
  await screenshot(page, "detailed-chat-order.png");

  await page.locator('.widget-head button[title]').first().click();
  record("CHAT-04-HISTORY", await page.locator(".conversation-history").isVisible(), await page.locator(".conversation-history").innerText());
  await page.goto(`${base}/portal`, { waitUntil: "networkidle" });
  await page.locator(".chat-launcher").click();
  await page.locator('.widget-head button[title]').first().click();
  await page.locator(".conversation-history .new-chat").click();

  before = await page.locator(".message.agent").count();
  await page.locator(".widget-form input").fill(`${marker} \u0110i\u1ec1u ki\u1ec7n tr\u1ea3 h\u00e0ng v\u00e0 b\u1eb1ng ch\u1ee9ng c\u1ea7n c\u00f3 l\u00e0 g\u00ec?`);
  await page.locator(".widget-form button").click();
  await waitForAgent(page, before);
  latest = page.locator(".message.agent").last();
  const kbAnswer = await latest.innerText();
  const citations = await latest.locator(".citation").count();
  const returnCitations = await latest.locator(".citation").allInnerTexts();
  record("CHAT-05-KB-ANSWER", kbAnswer.length > 120, kbAnswer);
  record("CHAT-06-CITATIONS", citations > 0, { citations, returnCitations });
  record("CHAT-07-CITATION-RELEVANCE", returnCitations.every((text) => /Tr\u1ea3 h\u00e0ng|Ho\u00e0n ti\u1ec1n/i.test(text)), returnCitations);
  await screenshot(page, "detailed-chat-kb.png");

  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".chat-launcher").click();
  await page.locator('.widget-head button[title]').first().click();
  const persistedHistory = await page.locator(".conversation-history").innerText();
  record("CHAT-08-PERSISTENCE", persistedHistory.includes(marker), persistedHistory.slice(0, 900));

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const mobilePage = await mobile.newPage();
  await login(mobilePage, "user2@test.com", "user");
  await mobilePage.waitForURL(/\/portal/, { timeout: 15_000 });
  await mobilePage.locator(".chat-launcher").click();
  const popup = await mobilePage.locator(".chat-popup").boundingBox();
  record("MOBILE-01-CHAT", Boolean(popup && popup.x >= 0 && popup.width <= 390 && popup.height <= 844), popup);
  await screenshot(mobilePage, "detailed-mobile.png");
  await mobile.close();

  record("BROWSER-01-NO-ERRORS", browserErrors.length === 0, browserErrors);
} catch (error) {
  results.push({ id: "SUITE", status: "FAIL", actual: error.stack || error.message });
  await screenshot(page, "detailed-suite-failure.png").catch(() => {});
}

const report = {
  generatedAt: new Date().toISOString(),
  marker,
  passed: results.filter((item) => item.status === "PASS").length,
  failed: results.filter((item) => item.status === "FAIL").length,
  total: results.length,
  results,
  browserErrors,
};
await fs.writeFile(`${output}/detailed-regression.json`, JSON.stringify(report, null, 2));
console.log(JSON.stringify({ passed: report.passed, failed: report.failed, total: report.total, failures: results.filter((item) => item.status === "FAIL") }, null, 2));
await browser.close();
