import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { compileFromFile } from "json-schema-to-typescript";
import prettier from "prettier";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const schemaPath = path.join(packageRoot, "schemas", "contracts-v1.json");
const outputPath = path.join(packageRoot, "src", "generated", "contracts-v1.ts");
const checkOnly = process.argv.includes("--check");

const generated = await compileFromFile(schemaPath, {
  bannerComment: "/* Generated from schemas/contracts-v1.json. Do not edit by hand. */",
  unreachableDefinitions: true,
});
const prettierConfig = (await prettier.resolveConfig(packageRoot)) ?? {};
const expected = await prettier.format(generated, {
  ...prettierConfig,
  parser: "typescript",
});

if (checkOnly) {
  const current = await readFile(outputPath, "utf8").catch(() => "");
  if (current !== expected) {
    throw new Error("generated contracts are stale; run `pnpm contracts:generate`");
  }
} else {
  await writeFile(outputPath, expected);
}
