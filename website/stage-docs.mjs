import { copyFileSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const source = "../docs";
const guides = [];
for (const directory of [".content", ".assets"]) {
  rmSync(directory, { recursive: true, force: true });
  mkdirSync(directory);
}

for (const filename of readdirSync(source)) {
  if (!filename.endsWith(".md") || filename === "404.md") continue;
  const id = filename.slice(0, -3);
  let page = readFileSync(resolve(source, filename), "utf8");
  if (id === "index" && !/^slug:\s*\/\s*$/m.test(page)) {
    page = page.replace(/^---\r?\n/, "---\nslug: /\n");
  }
  const order = Number(page.match(/^nav_order:\s*(\d+)$/m)?.[1] ?? Infinity);
  guides.push({ id, order });
  writeFileSync(resolve(".content", filename), page);
}

const order = ["index", "deployment", "api", "mcp", "development"];
guides.sort((a, b) => {
  if (a.order !== b.order) return a.order - b.order;
  if (order.includes(a.id) && order.includes(b.id)) return order.indexOf(a.id) - order.indexOf(b.id);
  return a.id.localeCompare(b.id);
});
writeFileSync("guide-order.mjs", "export const guides = " + JSON.stringify(guides.map(({ id }) => id)) + ";\n");
copyFileSync(resolve(source, "llms.txt"), ".assets/llms.txt");
const spec = process.env.OPENAPI_FILE || "openapi.yaml";
mkdirSync(".assets/reference");
copyFileSync(resolve("..", spec), ".assets/reference/openapi.yaml");
