# LLM Model Mapping & Compatibility Guide

This guide provides a deep dive into the `mappings` feature and the physical protocol boundaries between major LLM families.

## 1. The Mapping Philosophy: "Addition Over Modification"

The `mappings` section is a **Logical Adapter Layer**. It allows you to:

1. **Satisfy Hardcoded Tools**: Redirect requests from tools like Aider/Cursor that insist on `gpt-4`.
2. **Environment Switching**: Map a generic name to different physical backends across `profiles`.

## 2. Protocol Boundaries: The "Physical" Risk

Model names are just strings, but Protocols are **Architectural Contracts**. Mapping across incompatible protocols will fail unless a translation layer (Gateway) is used.

### The Big Three Protocol Families

| Feature            | **OpenAI** (`openai-v1`)       | **Anthropic** (`anthropic-v1`) | **Gemini** (`google-v1`)    |
| :----------------- | :----------------------------- | :----------------------------- | :-------------------------- |
| **Message Root**   | `messages: []`                 | `messages: []`                 | `contents: []`              |
| **User Role**      | `user`                         | `user`                         | `user`                      |
| **Assistant Role** | `assistant`                    | `assistant`                    | `model`                     |
| **System Prompt**  | Inside `messages` as `system`  | Top-level `system` string      | `system_instruction` object |
| **Structure**      | Content is `string` or `array` | Content is `array` of blocks   | Part of `parts` array       |

---

## 3. Deep Compatibility Matrix

Mapping `gpt-4` (OpenAI) to another model? Check this table for "Physical Collisions":

### A. Tool Calling (The Highest Risk)

- **OpenAI**: Uses `tool_calls: [...]` in the assistant message and `tool_call_id` in the tool result.
- **Gemini**: Uses `functionCall` part in a message and `functionResponse` part in the follow-up.
- **Collision**: An OpenAI-based tool will send a JSON with `tools`. Gemini will return 400 because it expects a different schema or `generationConfig`.

### B. Multi-modal / Vision

- **OpenAI**: `{"type": "image_url", "image_url": {"url": "..."}}`
- **Gemini**: `{"inlineData": {"mimeType": "image/jpeg", "data": "..."}}`
- **Collision**: Gemini does **not** natively support fetching images from a URL via the API message body (it requires the data inline or in Cloud Storage).

### C. Safety & Parameters

- **Gemini**: Has unique `safetySettings` (HARM*CATEGORY*...) which have no direct equivalent in OpenAI.
- **OpenAI**: Uses `presence_penalty` and `frequency_penalty`.

---

## 4. Best Practices for Safe Mapping

### ✅ Recommended: Same-Protocol Mapping

Mapping across models that share the OpenAI-compatible API is 100% safe.

- `gpt-4` -> `deepseek-chat` (Safe)
- `gpt-4` -> `qwen-max` (Safe)
- `gpt-4` -> `llama-3` (via Groq/vLLM) (Safe)

### ⚠️ Warning: Cross-Protocol Mapping

Mapping across different physical protocols requires a **Protocol Gateway**.

- `gpt-4` (OpenAI) -> `claude-3` (Anthropic) (Requires LiteLLM/OneAPI)
- `gpt-4` (OpenAI) -> `gemini-1.5` (Google) (Requires LiteLLM/OneAPI)

### 🛡️ Defensive Configuration

Always declare the protocol for internal models:

```yaml
models:
  internal-gemini:
    provider: google
    model: gemini-1.5-pro
    protocol: google-v1 # Signal to the caller: Do NOT use OpenAI SDK payloads!
```
