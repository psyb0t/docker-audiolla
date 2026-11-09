---
title: "Agent integrations"
description: "Install the audiolla agent skill and plugins for Claude Code, Codex and OpenClaw, or point any MCP client at the server's /v1/mcp endpoint."
nav_order: 19
---

# Agent integrations

The repository ships an agent skill and plugin manifests under [.agents/](https://github.com/psyb0t/docker-audiolla/tree/main/.agents). They teach an agent how to call a running audiolla server; none of them runs the server for you. Start one first ([getting started](getting-started.md)).

| Piece | Path | What it is |
| --- | --- | --- |
| Skill | [.agents/skills/audiolla/](https://github.com/psyb0t/docker-audiolla/tree/main/.agents/skills/audiolla) | Instructions and curl patterns for the REST API, plus [references/setup.md](https://github.com/psyb0t/docker-audiolla/blob/main/.agents/skills/audiolla/references/setup.md) for standing a server up. |
| Claude Code plugin | [.agents/.claude-plugin/plugin.json](https://github.com/psyb0t/docker-audiolla/blob/main/.agents/.claude-plugin/plugin.json) | Packages the skill and asks for the server URL and token. |
| Codex plugin | [.agents/.codex-plugin/plugin.json](https://github.com/psyb0t/docker-audiolla/blob/main/.agents/.codex-plugin/plugin.json) | Packages the skill for Codex. |
| OpenClaw plugin | [.agents/plugins/audiolla/](https://github.com/psyb0t/docker-audiolla/tree/main/.agents/plugins/audiolla) | `@psyb0t/audiolla`, a stdio bridge to `/v1/mcp` built on `mcp-remote`. |
| MCP Registry entry | [server.json](https://github.com/psyb0t/docker-audiolla/blob/main/server.json) | Lists the image as `io.github.psyb0t/audiolla` on the official MCP Registry. |

The skill works in any agent that reads `.agents/skills/`, such as [peen](https://github.com/psyb0t/peen).

## Claude Code

```bash
claude plugin marketplace add psyb0t/agents
claude plugin install audiolla@psyb0t
```

Claude Code asks for the audiolla URL and, if the server has auth on, the token. It stores the token in your OS keychain.

## Codex

```bash
codex plugin marketplace add psyb0t/agents
codex plugin add audiolla@psyb0t
```

Installed from the marketplace, the skill is invoked as `$audiolla:audiolla`. Codex also picks the skill up without any install in a repository that contains `.agents/skills/`, where it is invoked as `$audiolla`.

## OpenClaw

The skill is published to ClawHub on every release:

```bash
openclaw skills install @psyb0t/audiolla
```

For MCP clients that only speak local stdio, the `@psyb0t/audiolla` plugin bridges to the server's `/v1/mcp` endpoint:

```bash
openclaw plugins install clawhub:@psyb0t/audiolla
```

Then set `AUDIOLLA_URL` (for example `http://localhost:8000`; the bridge appends `/v1/mcp`) and, if the server has auth on, `AUDIOLLA_AUTH_TOKEN` in the plugin's environment. The bridge passes the token to `mcp-remote` as an `Authorization` header and writes nothing but MCP traffic to stdout.

## Any MCP client

A client that supports remote Streamable HTTP servers needs no plugin. Point it at `http://<host>:8000/v1/mcp` and add `Authorization: Bearer <token>` when auth is on. The [MCP server](mcp.md) page lists the tools.
