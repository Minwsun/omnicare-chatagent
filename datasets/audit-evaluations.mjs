import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const files = process.argv.slice(2).filter((item) => !item.startsWith("--"));
const targets = files.length ? files : ["evaluation.json", "evaluation-live.json", "evaluation-marketplaces.json"];
const outputArg = process.argv.find((item) => item.startsWith("--output="));
const output = resolve(outputArg?.split("=")[1] || resolve(root, "artifacts/evaluation-audit.json"));

function normalize(value) {
  return value.toLocaleLowerCase("vi").normalize("NFD").replace(/\p{Diacritic}/gu, "").replace(/[^a-z0-9]+/g, " ").trim();
}

function expand(rows) {
  return rows.flatMap((item) => item.message ? [item] : (item.variants || []).map((message, index) => ({ ...item, id: `${item.id}_${index + 1}`, message })));
}

function validate(target, rows, cases) {
  const errors = [];
  const ids = new Set();
  for (const [index, item] of cases.entries()) {
    if (!item.id || typeof item.id !== "string") errors.push(`${target}[${index}]: missing id`);
    if (!item.message || typeof item.message !== "string") errors.push(`${target}[${index}]: missing message`);
    if ((!item.category || typeof item.category !== "string") && (!item.expectedIntent || typeof item.expectedIntent !== "string")) {
      errors.push(`${target}[${index}]: missing category or expectedIntent`);
    }
    if (ids.has(item.id)) errors.push(`${target}[${index}]: duplicate id ${item.id}`);
    ids.add(item.id);
  }
  const serialized = JSON.stringify(rows);
  if (/sk-[a-z0-9_-]{12,}/i.test(serialized) || /postgres(?:ql)?:\/\/[^:\s]+:[^@\s]+@/i.test(serialized)) {
    errors.push(`${target}: contains credential-like content`);
  }
  return errors;
}

const reports = [];
for (const target of targets) {
  const rows = JSON.parse(await readFile(resolve(root, target), "utf8"));
  const cases = expand(rows);
  const errors = validate(target, rows, cases);
  const groups = new Map();
  for (const item of cases) {
    const key = normalize(item.message);
    groups.set(key, [...(groups.get(key) || []), item.id]);
  }
  const duplicates = [...groups.entries()].filter(([, ids]) => ids.length > 1).map(([text, ids]) => ({ fingerprint: createHash("sha256").update(text).digest("hex").slice(0, 12), ids }));
  reports.push({ file: target, templates: rows.length, cases: cases.length, unique: groups.size, duplicateCases: cases.length - groups.size, duplicates, errors });
}

await writeFile(output, `${JSON.stringify({ generatedAt: new Date().toISOString(), reports }, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ output, reports: reports.map(({ file, cases, unique, duplicateCases }) => ({ file, cases, unique, duplicateCases })) }));
if (reports.some((report) => report.errors.length || report.duplicateCases)) process.exitCode = 1;
