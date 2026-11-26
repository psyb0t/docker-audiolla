---
title: "REST API"
description: "Browse Audiolla's generated OpenAPI reference for REST operations, request fields, allowed values, examples and responses."
nav_order: 17
---

# REST API

Choose an operation in the sidebar to see its parameters, allowed values, request example and responses. The reference is generated from [OpenAPI YAML](/reference/openapi.yaml).

Start with the [upload operation](/reference/files-put/) to stage a file, [audio analysis](/reference/analyze/) to get JSON back, or [stem separation](/reference/separate/) to produce an audio file.

## Basics

The default local URL is `http://localhost:8000`. When `AUDIOLLA_AUTH_TOKEN` is set, send `Authorization: Bearer <token>`. The [health check](/reference/healthz/) is always open.

- [Getting started](getting-started.md) walks through staging, processing and retrieving audio.
- [Files and remote URLs](files.md) covers shared storage, file retention and fetching from allowed hosts.
- [Async jobs and webhooks](jobs.md) covers background requests and retrieving their results.
- [MCP server](mcp.md) explains how to use the tools at `/v1/mcp`.

The running server also serves the OpenAPI JSON at `/openapi.json` and interactive documentation at `/docs` and `/redoc`.
