# LangChain4j + Feishu remote MCP demo

Small **plain Java** program (no Spring) that wires **OpenAI** as the chat model and **Feishu’s hosted MCP** as a `ToolProvider` using `StreamableHttpMcpTransport` and `customHeaders` for Feishu’s `X-Lark-MCP-*` headers.

## Prerequisites

- JDK 21+
- Maven 3.9+

## Configure

| Environment variable | Purpose |
|----------------------|---------|
| `OPENAI_API_KEY` | Required |
| `OPENAI_MODEL` | Optional; defaults to `gpt-4o-mini` |
| `FEISHU_MCP_TOKEN` | Required; TAT or UAT string |
| `FEISHU_MCP_TOKEN_HEADER` | Optional; defaults to `X-Lark-MCP-TAT` (use `X-Lark-MCP-UAT` for a user token) |
| `FEISHU_MCP_ALLOWED_TOOLS` | Optional; forwarded to `X-Lark-MCP-Allowed-Tools` |
| `FEISHU_MCP_URL` | Optional; defaults to `https://mcp.feishu.cn/mcp` |

Official Feishu remote MCP details: [开发者调用远程 MCP 服务](https://open.feishu.cn/document/mcp_open_tools/developers-call-remote-mcp-server).

## Run

```bash
cd demo-langchain4j-feishu-mcp
export OPENAI_API_KEY=...
export FEISHU_MCP_TOKEN=...
export FEISHU_MCP_ALLOWED_TOOLS=fetch-doc,search-doc
mvn -q exec:java -Dexec.args="Summarize what you can do with the configured Feishu tools."
```

## Notes

- `langchain4j-mcp` tracks the LangChain4j **beta** line version aligned with the BOM (for `1.14.1` this is `1.14.1-beta24`, managed by `langchain4j-bom`).
- This sample does not start an HTTP server; it is a CLI-style agent entry point suitable to copy into a larger service.
