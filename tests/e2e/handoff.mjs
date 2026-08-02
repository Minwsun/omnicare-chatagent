import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";

const base = process.env.WEB_BASE_URL || "http://localhost:3100";
const marker = `HANDOFF-${Date.now()}`;
const browser = await chromium.launch({ headless: true });
const results = [];
const record = (id, passed, actual) => results.push({ id, status: passed ? "PASS" : "FAIL", actual });

async function login(page, email, password, route) {
  await page.goto(`${base}/login`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  const pending = page.waitForResponse(response => response.url().includes("/api/auth/login") && response.request().method() === "POST");
  await page.locator("form button").click();
  const response = await pending;
  if (!response.ok()) throw new Error(`LOGIN_${response.status()}`);
  await page.waitForURL(new RegExp(`${route}(?:$|/)`), { timeout: 60_000 });
}

const customerContext = await browser.newContext();
const adminContext = await browser.newContext();
const customer = await customerContext.newPage();
const admin = await adminContext.newPage();

try {
  await login(customer, "user1@test.com", "user", "/portal");
  await customer.locator(".chat-launcher").click();
  customer.once("dialog", dialog => dialog.accept());
  await customer.getByRole("button", { name: "Gặp nhân viên" }).click();
  await customer.locator(".handoff-card").waitFor({ timeout: 30_000 });
  const customerCard = await customer.locator(".handoff-card").innerText();
  const ticketId = customerCard.match(/TCK-[A-Z0-9-]+/)?.[0];
  record("CUSTOMER-CREATES-HANDOFF", Boolean(ticketId), customerCard);

  await login(admin, "admin@test.com", "admin", "/admin");
  await admin.goto(`${base}/admin/inbox`, { waitUntil: "networkidle", timeout: 60_000 });
  await admin.locator(".ticket-queue>button").filter({ hasText: ticketId }).click();
  await admin.getByRole("button", { name: "Nhận xử lý" }).click();
  await admin.getByPlaceholder("Nhập phản hồi cho khách hàng").waitFor({ timeout: 30_000 });
  record("ADMIN-CLAIMS", true, ticketId);

  const runsBefore = await admin.evaluate(async id => {
    const response = await fetch(`/api/admin/tickets/${id}`);
    return (await response.json()).ticket.conversation.aiRuns.length;
  }, ticketId);
  await customer.locator('.widget-form input:not([type="file"])').fill("Tôi bổ sung thêm thông tin sau khi nhân viên nhận xử lý.");
  await customer.locator('.widget-form button[type="submit"],.widget-form>button').last().click();
  await customer.getByText("Mình đã gửi tin nhắn này tới nhân viên đang hỗ trợ bạn.", { exact: true }).waitFor({ timeout: 20_000 });
  const runsAfter = await admin.evaluate(async id => {
    const response = await fetch(`/api/admin/tickets/${id}`);
    return (await response.json()).ticket.conversation.aiRuns.length;
  }, ticketId);
  record("HUMAN-OWNERSHIP-STOPS-AI", runsAfter === runsBefore, { runsBefore, runsAfter });

  await admin.getByPlaceholder("Nhập phản hồi cho khách hàng").fill(`Nhân viên đã tiếp nhận ${marker}`);
  await admin.getByRole("button", { name: "Gửi", exact: true }).click();
  await customer.getByText(`Nhân viên đã tiếp nhận ${marker}`, { exact: true }).waitFor({ timeout: 20_000 });
  record("ADMIN-REPLY-REACHES-CUSTOMER", true, marker);

  await admin.getByRole("button", { name: "Đã xử lý" }).click();
  await customer.waitForTimeout(5000);
  record("RESOLVE-REMOVES-ACTIVE-HANDOFF", await customer.locator(".handoff-card").count() === 0, await customer.locator(".handoff-card").count());
} catch (error) {
  results.push({ id: "SUITE", status: "FAIL", actual: error instanceof Error ? error.stack : String(error) });
}

await mkdir("output/playwright", { recursive: true });
const report = { generatedAt: new Date().toISOString(), base, marker, passed: results.filter(item => item.status === "PASS").length, failed: results.filter(item => item.status === "FAIL").length, results };
await writeFile("output/playwright/handoff-release.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
await browser.close();
if (report.failed) process.exitCode = 1;
