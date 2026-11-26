import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { inflateSync } from "node:zlib";

const guidePath = ".content/api.md";
const referencePath = ".content/reference";
const legacyLinks = [];

for (const name of readdirSync(referencePath)) {
  if (!name.endsWith(".api.mdx")) continue;
  const content = readFileSync(referencePath + "/" + name, "utf8");
  const encoded = content.match(/^api: (.+)$/m)?.[1];
  if (!encoded) throw new Error("Missing OpenAPI operation in " + name);
  const { method, path } = JSON.parse(inflateSync(Buffer.from(encoded, "base64")));
  const anchor = `${method} ${path}`.toLowerCase().replace(/[^\w -]/g, "").replaceAll(" ", "-");
  const slug = encodeURIComponent(name.slice(0, -".api.mdx".length));
  legacyLinks.push(
    `<a class="legacy-api-link" id="${anchor}" href="../reference/${slug}/">Open this operation in the REST API reference</a>`,
  );
}

const guide = readFileSync(guidePath, "utf8");
writeFileSync(guidePath, guide + "\n" + legacyLinks.join("\n") + "\n");
