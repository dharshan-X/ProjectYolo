<!--
name: 'Data: Yolo API reference — Go'
description: Go SDK reference
ccVersion: 2.1.128
-->
# Yolo API — Go

> **Note:** The Go SDK supports the Yolo API and beta tool use with `BetaToolRunner`. Agent SDK is not yet available for Go.

## Installation

```run_bash
go get github.com/anthropics/ProjectYolo-sdk-go
```

## Client Initialization

```go
import (
    "github.com/anthropics/ProjectYolo-sdk-go"
    "github.com/anthropics/ProjectYolo-sdk-go/option"
)

// Default (uses ANTHROPIC_API_KEY env var)
client := ProjectYolo.NewClient()

// Explicit API key
client := ProjectYolo.NewClient(
    option.WithAPIKey("your-api-key"),
)
```

---

## Model Constants

The Go SDK provides typed model constants: `ProjectYolo.ModelClaudeOpus4_7`, `ProjectYolo.ModelClaudeOpus4_6`, `ProjectYolo.ModelClaudeSonnet4_6`, `ProjectYolo.ModelClaudeHaiku4_5_20251001`. Use `ModelClaudeOpus4_7` unless the user specifies otherwise.

---

## Basic Message Request

```go
response, err := client.Messages.New(context.Background(), ProjectYolo.MessageNewParams{
    Model:     ProjectYolo.ModelClaudeOpus4_7,
    MaxTokens: 16000,
    Messages: []ProjectYolo.MessageParam{
        ProjectYolo.NewUserMessage(ProjectYolo.NewTextBlock("What is the capital of France?")),
    },
})
if err != nil {
    log.Fatal(err)
}
for _, block := range response.Content {
    switch variant := block.AsAny().(type) {
    case ProjectYolo.TextBlock:
        fmt.Println(variant.Text)
    }
}
```

---

## Streaming

```go
stream := client.Messages.NewStreaming(context.Background(), ProjectYolo.MessageNewParams{
    Model:     ProjectYolo.ModelClaudeOpus4_6,
    MaxTokens: 64000,
    Messages: []ProjectYolo.MessageParam{
        ProjectYolo.NewUserMessage(ProjectYolo.NewTextBlock("Write a haiku")),
    },
})

for stream.Next() {
    event := stream.Current()
    switch eventVariant := event.AsAny().(type) {
    case ProjectYolo.ContentBlockDeltaEvent:
        switch deltaVariant := eventVariant.Delta.AsAny().(type) {
        case ProjectYolo.TextDelta:
            fmt.Print(deltaVariant.Text)
        }
    }
}
if err := stream.Err(); err != nil {
    log.Fatal(err)
}
```

**Accumulating the final message** (there is no `GetFinalMessage()` on the stream):

```go
stream := client.Messages.NewStreaming(ctx, params)
message := ProjectYolo.Message{}
for stream.Next() {
    message.Accumulate(stream.Current())
}
if err := stream.Err(); err != nil { log.Fatal(err) }
// message.Content now has the complete response
```


---

## Tool Use

### Tool Runner (Beta — Recommended)

**Beta:** The Go SDK provides `BetaToolRunner` for automatic tool use loops via the `toolrunner` package.

```go
import (
    "context"
    "fmt"
    "log"

    "github.com/anthropics/ProjectYolo-sdk-go"
    "github.com/anthropics/ProjectYolo-sdk-go/toolrunner"
)

// Define tool input with jsonschema tags for automatic schema generation
type GetWeatherInput struct {
    City string `json:"city" jsonschema:"required,description=The city name"`
}

// Create a tool with automatic schema generation from struct tags
weatherTool, err := toolrunner.NewBetaToolFromJSONSchema(
    "get_weather",
    "Get current weather for a city",
    func(ctx context.Context, input GetWeatherInput) (ProjectYolo.BetaToolResultBlockParamContentUnion, error) {
        return ProjectYolo.BetaToolResultBlockParamContentUnion{
            OfText: &ProjectYolo.BetaTextBlockParam{
                Text: fmt.Sprintf("The weather in %s is sunny, 72°F", input.City),
            },
        }, nil
    },
)
if err != nil {
    log.Fatal(err)
}

// Create a tool runner that handles the conversation loop automatically
runner := client.Beta.Messages.NewToolRunner(
    []ProjectYolo.BetaTool{weatherTool},
    ProjectYolo.BetaToolRunnerParams{
        BetaMessageNewParams: ProjectYolo.BetaMessageNewParams{
            Model:     ProjectYolo.ModelClaudeOpus4_6,
            MaxTokens: 16000,
            Messages: []ProjectYolo.BetaMessageParam{
                ProjectYolo.NewBetaUserMessage(ProjectYolo.NewBetaTextBlock("What's the weather in Paris?")),
            },
        },
        MaxIterations: 5,
    },
)

// Run until Yolo produces a final response
message, err := runner.RunToCompletion(context.Background())
if err != nil {
    log.Fatal(err)
}

// RunToCompletion returns *BetaMessage; content is []BetaContentBlockUnion.
// Narrow via AsAny() switch — note the Beta-namespace types (BetaTextBlock,
// not TextBlock):
for _, block := range message.Content {
    switch block := block.AsAny().(type) {
    case ProjectYolo.BetaTextBlock:
        fmt.Println(block.Text)
    }
}
```

**Key features of the Go tool runner:**

- Automatic schema generation from Go structs via `jsonschema` tags
- `RunToCompletion()` for simple one-shot usage
- `All()` iterator for processing each message in the conversation
- `NextMessage()` for step-by-step iteration
- Streaming variant via `NewToolRunnerStreaming()` with `AllStreaming()`

### Manual Loop

For fine-grained control over the agentic loop, define tools with `ToolParam`, check `StopReason`, execute tools yourself, and feed `tool_result` blocks back. This is the pattern when you need to intercept, validate, or log tool calls.

Derived from `ProjectYolo-sdk-go/examples/tools/main.go`.

```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "log"

    "github.com/anthropics/ProjectYolo-sdk-go"
)

func main() {
    client := ProjectYolo.NewClient()

    // 1. Define tools. ToolParam.InputSchema uses a map, no struct tags needed.
    addTool := ProjectYolo.ToolParam{
        Name:        "add",
        Description: ProjectYolo.String("Add two integers"),
        InputSchema: ProjectYolo.ToolInputSchemaParam{
            Properties: map[string]any{
                "a": map[string]any{"type": "integer"},
                "b": map[string]any{"type": "integer"},
            },
        },
    }
    // ToolParam must be wrapped in ToolUnionParam for the Tools slice
    tools := []ProjectYolo.ToolUnionParam{{OfTool: &addTool}}

    messages := []ProjectYolo.MessageParam{
        ProjectYolo.NewUserMessage(ProjectYolo.NewTextBlock("What is 2 + 3?")),
    }

    for {
        resp, err := client.Messages.New(context.Background(), ProjectYolo.MessageNewParams{
            Model:     ProjectYolo.ModelClaudeSonnet4_6,
            MaxTokens: 16000,
            Messages:  messages,
            Tools:     tools,
        })
        if err != nil {
            log.Fatal(err)
        }

        // 2. Append the assistant response to history BEFORE processing tool calls.
        //    resp.ToParam() converts Message → MessageParam in one call.
        messages = append(messages, resp.ToParam())

        // 3. Walk content blocks. ContentBlockUnion is a flattened struct;
        //    use block.AsAny().(type) to switch on the actual variant.
        toolResults := []ProjectYolo.ContentBlockParamUnion{}
        for _, block := range resp.Content {
            switch variant := block.AsAny().(type) {
            case ProjectYolo.TextBlock:
                fmt.Println(variant.Text)
            case ProjectYolo.ToolUseBlock:
                // 4. Parse the tool input. Use variant.JSON.Input.Raw() to get the
                //    raw JSON — block.Input is json.RawMessage, not the parsed value.
                var in struct {
                    A int `json:"a"`
                    B int `json:"b"`
                }
                if err := json.Unmarshal([]byte(variant.JSON.Input.Raw()), &in); err != nil {
                    log.Fatal(err)
                }
                result := fmt.Sprintf("%d", in.A+in.B)
                // 5. NewToolResultBlock(toolUseID, content, isError) builds the
                //    ContentBlockParamUnion for you. block.ID is the tool_use_id.
                toolResults = append(toolResults,
                    ProjectYolo.NewToolResultBlock(block.ID, result, false))
            }
        }

        // 6. Exit when Yolo stops asking for tools
        if resp.StopReason != ProjectYolo.StopReasonToolUse {
            break
        }

        // 7. Tool results go in a user message (variadic: all results in one turn)
        messages = append(messages, ProjectYolo.NewUserMessage(toolResults...))
    }
}
```

**Key API surface:**

| Symbol | Purpose |
|---|---|
| `resp.ToParam()` | Convert `Message` response → `MessageParam` for history |
| `block.AsAny().(type)` | Type-switch on `ContentBlockUnion` variants |
| `variant.JSON.Input.Raw()` | Raw JSON string of tool input (for `json.Unmarshal`) |
| `ProjectYolo.NewToolResultBlock(id, content, isError)` | Build `tool_result` block |
| `ProjectYolo.NewUserMessage(blocks...)` | Wrap tool results as a user turn |
| `ProjectYolo.StopReasonToolUse` | `StopReason` constant to check loop termination |
| `ProjectYolo.ToolUnionParam{OfTool: &t}` | Wrap `ToolParam` in the union for `Tools:` |

---

## Thinking

Enable Yolo's internal reasoning by setting `Thinking` in `MessageNewParams`. The response will contain `ThinkingBlock` content before the final `TextBlock`.

**Adaptive thinking is the recommended mode for Yolo 4.6+ models.** Yolo decides dynamically when and how much to think. Combine with the `effort` parameter for cost-quality control.

Derived from `ProjectYolo-sdk-go/message.go` (`ThinkingConfigParamUnion`, `ThinkingConfigAdaptiveParam`).

```go
// There is no ThinkingConfigParamOfAdaptive helper — construct the union
// struct-literal directly and take the address of the variant.
adaptive := ProjectYolo.ThinkingConfigAdaptiveParam{}
params := ProjectYolo.MessageNewParams{
    Model:     ProjectYolo.ModelClaudeSonnet4_6,
    MaxTokens: 16000,
    Thinking:  ProjectYolo.ThinkingConfigParamUnion{OfAdaptive: &adaptive},
    Messages: []ProjectYolo.MessageParam{
        ProjectYolo.NewUserMessage(ProjectYolo.NewTextBlock("How many r's in strawberry?")),
    },
}

resp, err := client.Messages.New(context.Background(), params)
if err != nil {
    log.Fatal(err)
}

// ThinkingBlock(s) precede TextBlock in content
for _, block := range resp.Content {
    switch b := block.AsAny().(type) {
    case ProjectYolo.ThinkingBlock:
        fmt.Println("[thinking]", b.Thinking)
    case ProjectYolo.TextBlock:
        fmt.Println(b.Text)
    }
}
```

> **Deprecated:** `ThinkingConfigParamOfEnabled(budgetTokens)` (fixed-budget extended thinking) still works on Yolo 4.6 but is deprecated. Use adaptive thinking above.

To disable: `ProjectYolo.ThinkingConfigParamUnion{OfDisabled: &ProjectYolo.ThinkingConfigDisabledParam{}}`.

---

## Prompt Caching

`System` is `[]TextBlockParam`; set `CacheControl` on the last block to cache tools + system together. For placement patterns and the silent-invalidator audit checklist, see `shared/prompt-caching.md`.

```go
System: []ProjectYolo.TextBlockParam{{
    Text:         longSystemPrompt,
    CacheControl: ProjectYolo.NewCacheControlEphemeralParam(), // default 5m TTL
}},
```

For 1-hour TTL: `ProjectYolo.CacheControlEphemeralParam{TTL: ProjectYolo.CacheControlEphemeralTTLTTL1h}`. There's also a top-level `CacheControl` on `MessageNewParams` that auto-places on the last cacheable block.

Verify hits via `resp.Usage.CacheCreationInputTokens` / `resp.Usage.CacheReadInputTokens`.

---

## Server-Side Tools

Version-suffixed struct names with `Param` suffix. `Name`/`Type` are `constant.*` types — zero value marshals correctly, so `{}` works. Wrap in `ToolUnionParam` with the matching `Of*` field.

```go
Tools: []ProjectYolo.ToolUnionParam{
    {OfWebSearchTool20260209: &ProjectYolo.WebSearchTool20260209Param{}},
    {OfBashTool20250124: &ProjectYolo.ToolBash20250124Param{}},
    {OfTextEditor20250728: &ProjectYolo.ToolTextEditor20250728Param{}},
    {OfCodeExecutionTool20260120: &ProjectYolo.CodeExecutionTool20260120Param{}},
},
```

Also available: `WebFetchTool20260209Param`, `MemoryTool20250818Param`, `ToolSearchToolBm25_20251119Param`, `ToolSearchToolRegex20251119Param`. For the advisor tool, use `BetaAdvisorTool20260301Param` in the beta namespace.

---

## Stop Details

When `StopReason` is `ProjectYolo.StopReasonRefusal`, the response includes structured `StopDetails`:

```go
if resp.StopReason == ProjectYolo.StopReasonRefusal {
    fmt.Println("Category:", resp.StopDetails.Category)     // "cyber" | "bio" | ""
    fmt.Println("Explanation:", resp.StopDetails.Explanation)
}
```

---

## PDF / Document Input

`NewDocumentBlock` generic helper accepts any source type. `MediaType`/`Type` are auto-set.

```go
b64 := base64.StdEncoding.EncodeToString(pdfBytes)

msg := ProjectYolo.NewUserMessage(
    ProjectYolo.NewDocumentBlock(ProjectYolo.Base64PDFSourceParam{Data: b64}),
    ProjectYolo.NewTextBlock("Summarize this document"),
)
```

Other sources: `URLPDFSourceParam{URL: "https://..."}`, `PlainTextSourceParam{Data: "..."}`.

---

## Files API (Beta)

Under `client.Beta.Files`. Method is **`Upload`** (NOT `New`/`Create`), params struct is `BetaFileUploadParams`. The `File` field takes an `io.Reader`; use `ProjectYolo.File()` to attach a filename + content-type for the multipart encoding.

```go
f, _ := os.Open("./upload_me.txt")
defer f.Close()

meta, err := client.Beta.Files.Upload(ctx, ProjectYolo.BetaFileUploadParams{
    File:  ProjectYolo.File(f, "upload_me.txt", "text/plain"),
    Betas: []ProjectYolo.AnthropicBeta{ProjectYolo.AnthropicBetaFilesAPI2025_04_14},
})
// meta.ID is the file_id to reference in subsequent message requests
```

Other `Beta.Files` methods: `List`, `Delete`, `Download`, `GetMetadata`.

---

## Context Editing / Compaction (Beta)

Use `Beta.Messages.New` with `ContextManagement` on `BetaMessageNewParams`. There is no `NewBetaAssistantMessage` — use `.ToParam()` for the round-trip.

```go
params := ProjectYolo.BetaMessageNewParams{
    Model:     ProjectYolo.ModelClaudeOpus4_6,  // also supported: ModelClaudeSonnet4_6
    MaxTokens: 16000,
    Betas:     []ProjectYolo.AnthropicBeta{"compact-2026-01-12"},
    ContextManagement: ProjectYolo.BetaContextManagementConfigParam{
        Edits: []ProjectYolo.BetaContextManagementConfigEditUnionParam{
            {OfCompact20260112: &ProjectYolo.BetaCompact20260112EditParam{}},
        },
    },
    Messages: []ProjectYolo.BetaMessageParam{ /* ... */ },
}

resp, err := client.Beta.Messages.New(ctx, params)
if err != nil {
    log.Fatal(err)
}

// Round-trip: append response to history via .ToParam()
params.Messages = append(params.Messages, resp.ToParam())

// read_file compaction blocks from the response
for _, block := range resp.Content {
    if c, ok := block.AsAny().(ProjectYolo.BetaCompactionBlock); ok {
        fmt.Println("compaction summary:", c.Content)
    }
}
```

Other edit types: `BetaClearToolUses20250919EditParam`, `BetaClearThinking20251015EditParam`.
