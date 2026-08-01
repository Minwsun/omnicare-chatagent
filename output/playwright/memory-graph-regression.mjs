import { chromium } from "playwright";
import fs from "node:fs/promises";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const marker = "CUA-E2E-MEMORY-20260731";
const results = [];
const record = (id, passed, actual) => results.push({ id, status: passed ? "PASS" : "FAIL", actual });

async function send(text) {
  const before = await page.locator(".message.agent").count();
  await page.locator(".widget-form input").fill(text);
  await page.locator(".widget-form button").click();
  await page.waitForFunction((count) => document.querySelectorAll(".message.agent").length > count, before, { timeout: 120_000 });
  await page.waitForFunction(() => !document.querySelector(".widget-form button")?.hasAttribute("disabled"), null, { timeout: 120_000 });
  return page.locator(".message.agent").last().innerText();
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

  const first = await send(`${marker} Xem t\u00ecnh tr\u1ea1ng \u0111\u01a1n ORD-1181`);
  record("MEMORY-01-INITIAL", first.includes("ORD-1181"), first);

  const followUp = await send("C\u00f2n thanh to\u00e1n th\u00ec sao?");
  record("MEMORY-02-FOLLOW-UP", followUp.includes("ORD-1181"), followUp);

  const override = await send("Xem t\u00ecnh tr\u1ea1ng \u0111\u01a1n ORD-8743D67CB8");
  record("MEMORY-03-EXPLICIT-OVERRIDE", override.includes("ORD-8743D67CB8") && !override.includes("ORD-1181"), override);

  const secondFollowUp = await send("C\u00f2n thanh to\u00e1n th\u00ec sao?");
  record("MEMORY-04-UPDATED-CONTEXT", secondFollowUp.includes("ORD-8743D67CB8"), secondFollowUp);

  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".chat-launcher").click();
  const afterReload = await send("\u0110\u01a1n \u0111\u00f3 c\u00f3 h\u1ee7y \u0111\u01b0\u1ee3c kh\u00f4ng?");
  record("MEMORY-05-RELOAD", afterReload.includes("ORD-8743D67CB8"), afterReload);
  await page.screenshot({ path: "E:/Code _Project/ChatAgent/output/playwright/memory-graph-regression.png", fullPage: true });
} catch (error) {
  results.push({ id: "SUITE", status: "FAIL", actual: error.stack || error.message });
}

const report = { generatedAt: new Date().toISOString(), marker, passed: results.filter((item) => item.status === "PASS").length, failed: results.filter((item) => item.status === "FAIL").length, results };
await fs.writeFile("E:/Code _Project/ChatAgent/output/playwright/memory-graph-regression.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
await browser.close();
