package com.example.feishu.mcp.demo.config;

import io.modelcontextprotocol.client.transport.customizer.McpSyncHttpClientRequestCustomizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Feishu remote MCP authenticates with custom HTTP headers on every JSON-RPC POST.
 * Spring AI wires {@link McpSyncHttpClientRequestCustomizer} into the JDK HttpClient-based
 * streamable-HTTP MCP transport.
 *
 * @see <a href="https://open.feishu.cn/document/mcp_open_tools/developers-call-remote-mcp-server">Feishu MCP developer guide</a>
 */
@Configuration
public class FeishuMcpAuthConfiguration {

    @Bean
    McpSyncHttpClientRequestCustomizer feishuMcpRequestHeaders(
            @Value("${feishu.mcp.token:}") String token,
            @Value("${feishu.mcp.token-header:X-Lark-MCP-TAT}") String tokenHeaderName,
            @Value("${feishu.mcp.allowed-tools:}") String allowedTools) {
        return (builder, method, uri, body, context) -> {
            if (token != null && !token.isBlank()) {
                builder.header(tokenHeaderName, token);
            }
            if (allowedTools != null && !allowedTools.isBlank()) {
                builder.header("X-Lark-MCP-Allowed-Tools", allowedTools);
            }
        };
    }
}
