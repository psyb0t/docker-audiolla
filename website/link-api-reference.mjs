import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { inflateSync } from "node:zlib";

const guidePath = ".content/api.md";
const referencePath = ".content/reference";
const operationLinks = new Map();

for (const name of readdirSync(referencePath)) {
  if (!name.endsWith(".api.mdx")) continue;
  const content = readFileSync(referencePath + "/" + name, "utf8");
  const encoded = content.match(/^api: (.+)$/m)?.[1];
  if (!encoded) throw new Error("Missing OpenAPI operation in " + name);
  const item = JSON.parse(inflateSync(Buffer.from(encoded, "base64")));
  const endpoint = item.method.toUpperCase() + " " + item.path;
  operationLinks.set(endpoint, "./reference/" + name);
}

const guide = readFileSync(guidePath, "utf8");
const sections = guide.split(/(?=^## )/m);
const basics = sections.splice(0, 2).join("").replaceAll("REST API reference", "REST API");
const introduction = "Use the sidebar for request parameters, schemas, responses and curl examples. ";
const reference = "[Download the OpenAPI YAML](https://psyb0t.github.io/docker-audiolla/reference/openapi.yaml).";
const heading = basics.replace(/^This page is generated from .*$/m, introduction + reference);

const index = sections.map((section) => {
  const title = section.match(/^## .+$/m)?.[0];
  const rows = [...section.matchAll(/^### (\S+ \/\S+)$/gm)].map((match) => {
    const endpoint = match[1];
    const link = operationLinks.get(endpoint);
    if (!link) throw new Error("Legacy endpoint has no generated reference: " + endpoint);
    const anchor = endpoint.toLowerCase().replace(/[^\w -]/g, "").replaceAll(" ", "-");
    return '<a id="' + anchor + '"></a>\n\n- [`' + endpoint + '`](' + link + ')';
  });
  return title + "\n\n" + rows.join("\n\n");
}).join("\n\n");

writeFileSync(guidePath, heading + index + "\n");
