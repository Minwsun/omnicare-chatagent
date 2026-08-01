import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const seed = process.env.HOLDOUT_SEED || `${Date.now()}`;
const datasetDir = dirname(fileURLToPath(import.meta.url));
const output = resolve(process.argv[2] || resolve(datasetDir, "artifacts/evaluation-holdout.json"));
const templates = JSON.parse(await readFile(resolve(datasetDir, "evaluation-live.json"), "utf8"));

const prefixes = ["Cho mình hỏi,", "Mình cần biết:", "Bạn kiểm tra giúp", "Hỏi nhanh:", "Nhờ hỗ trợ"];
const suffixes = ["nhé", "giúp mình với", "được không?", "ạ", "mình đang cần gấp"];
const replacements = [
  ["tôi", "mình"], ["không", "ko"], ["được", "dc"], ["đơn", "đơn hàng"],
  ["kiểm tra", "xem giúp"], ["hủy", "huỷ"], ["trả hàng", "đổi trả"],
];

function hash(value) {
  return createHash("sha256").update(`${seed}:${value}`).digest();
}

function mutate(message, index) {
  const bytes = hash(`${message}:${index}`);
  if (index === 0) return `${prefixes[bytes[0] % prefixes.length]} ${message.charAt(0).toLowerCase()}${message.slice(1)}`;
  if (index === 1) return `${message.replace(...replacements[bytes[1] % replacements.length])} ${suffixes[bytes[2] % suffixes.length]}`;
  return `${prefixes[bytes[4] % prefixes.length]} ${message} ${suffixes[bytes[5] % suffixes.length]}`;
}

const intentByTemplate = {
  order_track: ["ORDER_TRACKING"], out_for_delivery: ["ORDER_TRACKING"], delivered_missing: ["ORDER_TRACKING"],
  cancel_unspecified: ["ORDER_CANCELLATION"], cancel_confirmed: ["ORDER_CANCELLATION"], cancel_shipped: ["ORDER_CANCELLATION"],
  foreign_order: ["ORDER_TRACKING", "ORDER_CANCELLATION", "PAYMENT_STATUS"], payment_status: ["PAYMENT_STATUS"],
  payment_policy: ["PAYMENT_POLICY"], refund_status: ["REFUND_STATUS"],
  return_delivered: ["RETURN_ELIGIBILITY"], return_policy: ["RETURN_POLICY", "REFUND_POLICY", "KNOWLEDGE"], voucher: ["VOUCHER"], account_security: ["ACCOUNT_SECURITY"],
  privacy: ["PRIVACY"], shipping_policy: ["SHIPPING_POLICY"], fraud_warning: ["FRAUD_WARNING", "ACCOUNT_SECURITY"],
  app_troubleshooting: ["TECHNICAL_SUPPORT"], prompt_injection: ["PROMPT_INJECTION"], out_of_scope: ["OUT_OF_SCOPE"],
};

const citationTerms = {
  payment_policy: ["thanh toán", "payment"], return_policy: ["trả hàng", "hoàn tiền", "return", "refund"],
  voucher: ["voucher", "mã giảm giá"], account_security: ["bảo mật", "tài khoản", "otp"],
  privacy: ["bảo mật", "dữ liệu", "privacy"], shipping_policy: ["vận chuyển", "giao hàng", "shipping"],
  fraud_warning: ["lừa đảo", "bảo mật", "an toàn"], app_troubleshooting: ["ứng dụng", "app", "thông báo"],
};

const cases = [];
for (const template of templates) {
  for (const [variantIndex, variant] of template.variants.entries()) {
    for (let mutation = 0; mutation < 3; mutation += 1) {
      cases.push({
        ...Object.fromEntries(Object.entries(template).filter(([key]) => key !== "variants")),
        id: `holdout_${hash(`${template.id}:${variantIndex}:${mutation}`).toString("hex").slice(0, 12)}`,
        message: mutate(variant, mutation),
        intentAnyOf: intentByTemplate[template.id],
        citationMustMentionAny: citationTerms[template.id],
        holdoutSeedHash: createHash("sha256").update(seed).digest("hex").slice(0, 12),
      });
    }
  }
}

const normalized = new Set(cases.map((item) => item.message.toLocaleLowerCase("vi").replace(/\s+/g, " ").trim()));
if (cases.length !== 300 || normalized.size !== 300) throw new Error(`Holdout must contain 300 unique cases; got ${cases.length}/${normalized.size}`);
await writeFile(output, `${JSON.stringify(cases, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ seedHash: cases[0].holdoutSeedHash, total: cases.length, unique: normalized.size, output }));
