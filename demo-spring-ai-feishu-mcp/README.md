# Spring AI + Feishu remote MCP demo

Minimal Spring Boot application that uses **Spring AI ChatClient** with tools discovered from **Feishu’s hosted MCP endpoint** (`https://mcp.feishu.cn/mcp` by default).

## Prerequisites

- JDK 21+
- Maven 3.9+
- An OpenAI-compatible key (`OPENAI_API_KEY`)
- A Feishu **tenant access token (TAT)** or **user access token (UAT)** with the scopes required by the tools you enable

## Configure

Environment variables (typical):

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Spring AI OpenAI chat model |
| `FEISHU_MCP_TOKEN` | Value for `X-Lark-MCP-TAT` or `X-Lark-MCP-UAT` |
| `FEISHU_MCP_TOKEN_HEADER` | Optional; defaults to `X-Lark-MCP-TAT`. Use `X-Lark-MCP-UAT` when passing a user token |
| `FEISHU_MCP_ALLOWED_TOOLS` | Optional; comma-separated tool names exposed to the model (Feishu recommends listing explicitly) |
| `FEISHU_MCP_BASE_URL` | Optional; defaults to `https://mcp.feishu.cn` |
| `FEISHU_MCP_ENDPOINT` | Optional; defaults to `/mcp` |

Official Feishu flow and headers are documented here: [开发者调用远程 MCP 服务](https://open.feishu.cn/document/mcp_open_tools/developers-call-remote-mcp-server).

## Run

```bash
cd demo-spring-ai-feishu-mcp
mvn spring-boot:run
```

## Try it

```bash
curl -sS http://localhost:8080/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"List the tools you can use, then fetch doc ... if appropriate."}'
```

## Notes

- This sample is intentionally small: it does **not** implement end-user OAuth for UAT; you supply tokens via environment variables as a service-style integration.
- If your Feishu account or transport differs (for example international Lark endpoints), adjust `FEISHU_MCP_BASE_URL` and follow the current Feishu/Lark platform documentation.
