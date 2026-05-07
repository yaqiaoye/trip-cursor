package com.example.feishu.mcp.demo.web;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ChatController {

    private final ChatClient chatClient;

    public ChatController(ChatModel chatModel, ToolCallbackProvider toolCallbackProvider) {
        this.chatClient = ChatClient.builder(chatModel).defaultToolCallbacks(toolCallbackProvider).build();
    }

    @PostMapping(path = "/api/chat", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.TEXT_PLAIN_VALUE)
    public String chat(@RequestBody ChatRequest request) {
        return chatClient.prompt(request.message()).call().content();
    }

    public record ChatRequest(String message) {}
}
