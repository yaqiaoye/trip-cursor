package com.example.feishu.mcp.demo;

import dev.langchain4j.mcp.McpToolProvider;
import dev.langchain4j.mcp.client.DefaultMcpClient;
import dev.langchain4j.mcp.client.McpClient;
import dev.langchain4j.mcp.client.transport.http.StreamableHttpMcpTransport;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.service.AiServices;
import dev.langchain4j.service.UserMessage;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Minimal LangChain4j program: OpenAI chat model + Feishu-hosted MCP tools over streamable HTTP.
 *
 * <p>Environment variables:
 *
 * <ul>
 *   <li>{@code OPENAI_API_KEY} &mdash; required
 *   <li>{@code FEISHU_MCP_TOKEN} &mdash; Feishu TAT or UAT value
 *   <li>{@code FEISHU_MCP_TOKEN_HEADER} &mdash; optional, defaults to {@code X-Lark-MCP-TAT}
 *   <li>{@code FEISHU_MCP_ALLOWED_TOOLS} &mdash; optional comma-separated tool allow-list header
 *   <li>{@code FEISHU_MCP_URL} &mdash; optional, defaults to {@code https://mcp.feishu.cn/mcp}
 * </ul>
 *
 * @see <a href="https://open.feishu.cn/document/mcp_open_tools/developers-call-remote-mcp-server">Feishu MCP developer guide</a>
 */
public final class FeishuMcpAgentDemo {

    public static void main(String[] args) {
        String openAiKey = requiredEnv("OPENAI_API_KEY");
        String feishuToken = requiredEnv("FEISHU_MCP_TOKEN");
        String tokenHeader = envOrDefault("FEISHU_MCP_TOKEN_HEADER", "X-Lark-MCP-TAT");
        String allowedTools = System.getenv("FEISHU_MCP_ALLOWED_TOOLS");
        String mcpUrl = envOrDefault("FEISHU_MCP_URL", "https://mcp.feishu.cn/mcp");

        Map<String, String> headers = new HashMap<>();
        headers.put(tokenHeader, feishuToken);
        if (allowedTools != null && !allowedTools.isBlank()) {
            headers.put("X-Lark-MCP-Allowed-Tools", allowedTools);
        }

        StreamableHttpMcpTransport transport =
                StreamableHttpMcpTransport.builder().url(mcpUrl).customHeaders(headers).build();

        McpClient mcpClient = DefaultMcpClient.builder().key("feishu").transport(transport).build();

        McpToolProvider toolProvider = McpToolProvider.builder().mcpClients(List.of(mcpClient)).build();

        OpenAiChatModel model = OpenAiChatModel.builder()
                .apiKey(openAiKey)
                .modelName(envOrDefault("OPENAI_MODEL", "gpt-4o-mini"))
                .build();

        Assistant assistant = AiServices.builder(Assistant.class)
                .chatModel(model)
                .toolProvider(toolProvider)
                .build();

        String prompt = args.length > 0 ? String.join(" ", args) : "Which MCP tools are available? Reply briefly.";
        try {
            System.out.println(assistant.chat(prompt));
        } finally {
            mcpClient.close();
        }
    }

    private static String requiredEnv(String name) {
        String v = System.getenv(name);
        if (v == null || v.isBlank()) {
            throw new IllegalStateException("Missing required environment variable: " + name);
        }
        return v;
    }

    private static String envOrDefault(String name, String def) {
        String v = System.getenv(name);
        return (v == null || v.isBlank()) ? def : v;
    }

    interface Assistant {
        String chat(@UserMessage String userMessage);
    }
}
