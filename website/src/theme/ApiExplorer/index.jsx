import React from "react";
import CodeBlock from "@theme/CodeBlock";

const shellQuote = (value) => "'" + String(value).replaceAll("'", "'\\''") + "'";
const endpoint = "http://localhost:8000";

export default function ApiExplorer({ item }) {
  const examples = item["x-codeSamples"] ?? [];
  const body = item.requestBody?.content ?? {};
  const query = new URLSearchParams();
  let path = item.path;
  for (const parameter of item.parameters ?? []) {
    const value = parameter.example ?? parameter.schema?.example ?? parameter.schema?.default;
    if (parameter.in === "path") {
      path = path.replace("{" + parameter.name + "}", encodeURIComponent(value ?? parameter.name));
    } else if (parameter.in === "query" && parameter.required) {
      query.set(parameter.name, value ?? parameter.name);
    }
  }
  const url = endpoint + path + (query.size ? "?" + query : "");
  const args = ["curl --fail-with-body", "-X " + item.method.toUpperCase(), shellQuote(url)];
  if (body["application/json"]) {
    const sample = body["application/json"].example ?? item.jsonRequestBodyExample;
    args.push("-H 'Content-Type: application/json'");
    if (sample !== undefined) args.push("--data " + shellQuote(JSON.stringify(sample, null, 2)));
  } else if (body["application/octet-stream"] || body["image/png"]) {
    const media = body["image/png"] ? "image/png" : "application/octet-stream";
    args.push("-H " + shellQuote("Content-Type: " + media), "--data-binary @input");
  }

  const samples = examples.length ? examples : [{ label: "curl", source: args.join(" ") }];
  return samples.map(({ label, source }) => (
    <CodeBlock key={source} language="bash" title={label}>
      {source}
    </CodeBlock>
  ));
}
