import { chromium } from "playwright";
import fs from "node:fs/promises";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const result = { passed: false, citations: 0, answer: "", errors: [] };

page.on("console", (message) => {
  if (message.type() === "error") result.errors.push(message.text());
});

try {
  await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
  await page.locator('input[name="email"]').fill("user1@test.com");
  await page.locator('input[name="password"]').fill("user");
  await page.locator("form button").click();
  await page.waitForURL(/\/portal/, { timeout: 15_000 });
  await page.locator(".chat-launcher").click();
  await page.locator('.widget-head button[title]').first().click();
  await page.locator(".conversation-history button").first().click();
  await page.waitForTimeout(300);

  const messages = page.locator(".message.agent");
  const before = await messages.count();
  await page.locator(".widget-form input").fill("Điều kiện trả hàng và bằng chứng cần có là gì?");
  await page.locator(".widget-form button").click();
  await page.waitForFunction(
    (count) => document.querySelectorAll(".message.agent").length > count,
    before,
    { timeout: 120_000 },
  );
  await page.waitForFunction(
    () => !document.querySelector(".widget-form button")?.hasAttribute("disabled"),
    null,
    { timeout: 120_000 },
  );

  const latest = messages.last();
  result.answer = await latest.innerText();
  result.citations = await latest.locator(".citation").count();
  result.passed = result.answer.length > 30 && result.citations > 0;
  await page.screenshot({ path: "E:/Code _Project/ChatAgent/output/playwright/focused-citation.png", fullPage: true });
} catch (error) {
  result.errors.push(error.stack || error.message);
}

await fs.writeFile("E:/Code _Project/ChatAgent/output/playwright/focused-citation.json", JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
await browser.close();
