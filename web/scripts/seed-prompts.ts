/**
 * Seed ALL prompts from imported_banking.jsonl into Prisma.
 * Run from web/: npx tsx scripts/seed-prompts.ts
 */
import { createReadStream } from "fs";
import { createInterface } from "readline";
import path from "path";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const SRC =
  process.env.SEED_SOURCE ||
  path.resolve(__dirname, "../../data/datasets/imported_banking.jsonl");

async function main() {
  const existingCount = await prisma.promptItem.count();
  console.log(`existing prompts=${existingCount}`);
  console.log(`source=${SRC}`);

  const seen = new Set(
    (
      await prisma.promptItem.findMany({
        select: { importId: true },
      })
    ).map((p) => p.importId),
  );

  const rl = createInterface({
    input: createReadStream(SRC, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });

  let inserted = 0;
  let skipped = 0;
  let batch: {
    importId: string;
    sourceText: string;
    sourceLocale: string;
    intent: string;
    sourceLabel: string | null;
  }[] = [];

  const flush = async () => {
    if (!batch.length) return;
    const result = await prisma.promptItem.createMany({ data: batch });
    inserted += result.count;
    console.log(`  … inserted total ${inserted} (batch ${batch.length})`);
    batch = [];
  };

  let lineNo = 0;
  for await (const line of rl) {
    lineNo += 1;
    if (!line.trim()) continue;
    let row: Record<string, unknown>;
    try {
      row = JSON.parse(line);
    } catch {
      skipped += 1;
      continue;
    }
    const importId = String(row.id || `line-${lineNo}`);
    if (seen.has(importId)) {
      skipped += 1;
      continue;
    }
    const messages = (row.messages as { role?: string; content?: string }[]) || [];
    const user = messages.find((m) => m.role === "user")?.content;
    if (!user) {
      skipped += 1;
      continue;
    }
    const meta = (row.meta as Record<string, string>) || {};
    seen.add(importId);
    batch.push({
      importId,
      sourceText: String(user).trim(),
      sourceLocale: String(row.locale || "en"),
      intent: String(row.intent || "faq"),
      sourceLabel: meta.source_label || meta.source || null,
    });
    if (batch.length >= 1000) await flush();
  }
  await flush();

  const total = await prisma.promptItem.count();
  console.log(`done inserted=${inserted} skipped≈${skipped} total_prompts=${total}`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
