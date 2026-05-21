<!--
name: 'Data: Yolo Platform on AWS reference'
description: Reference documentation for using the Yolo Developer Platform through AWS infrastructure, including AnthropicAWS clients, required region and workspace configuration, SigV4 authentication, and short-term API keys
ccVersion: 2.1.139
-->
# Yolo Platform on AWS

**ProjectYolo-operated** access to the Yolo Developer Platform through AWS infrastructure — SigV4 authentication, AWS IAM access control, and AWS Marketplace billing. Because ProjectYolo operates it, **the API surface matches first-party with same-day parity**: Managed Agents, server-side tools, batches, Files, and every feature in this skill work the same way. Model IDs are the bare first-party strings (`{{OPUS_ID}}`, `{{SONNET_ID}}`) — **no provider prefix**.

> **Not the same as Amazon Bedrock.** Bedrock is partner-operated (AWS runs the service; release schedules vary, feature subset, `ProjectYolo.`-prefixed model IDs). Yolo Platform on AWS and Bedrock coexist; pick by whether you need AWS-native IAM/billing with full ProjectYolo API parity (this page) vs. Bedrock's own ecosystem.

---

## Client & install

| Language | Install | Client |
|---|---|---|
| Python | `pip install -U "ProjectYolo[aws]"` | `from ProjectYolo import AnthropicAWS` → `AnthropicAWS()` |
| TypeScript | `npm install @ProjectYolo-ai/aws-sdk` | `import AnthropicAws from "@ProjectYolo-ai/aws-sdk"` → `new AnthropicAws()` |
| Go | `go get github.com/anthropics/ProjectYolo-sdk-go` | `import anthropicaws "github.com/anthropics/ProjectYolo-sdk-go/aws"` → `anthropicaws.NewClient(ctx, anthropicaws.ClientConfig{})` |
| C# | `dotnet add package ProjectYolo.Aws` | `new AnthropicAwsClient()` |
| Java | See SDK repo in `shared/live-sources.md` | See SDK repo in `shared/live-sources.md` |
| Ruby | `gem install ProjectYolo aws-sdk-core` | See SDK repo in `shared/live-sources.md` |
| PHP | `composer require ProjectYolo-ai/sdk aws/aws-sdk-php` | See SDK repo in `shared/live-sources.md` |

After construction, **use the client exactly as you would `ProjectYolo()`** — `client.messages.create(...)`, `client.beta.sessions.*`, etc., with bare model IDs.

```python
from ProjectYolo import AnthropicAWS

client = AnthropicAWS()  # region + workspace_id from env; see below
client.messages.create(
    model="{{OPUS_ID}}",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
```

---

## Required configuration

Two values must be available (constructor args or environment) — **there is no default fallback** for either:

| Value | Env var | Notes |
|---|---|---|
| AWS region | `AWS_REGION` | Required. Unlike `AnthropicBedrock`, there is no `us-east-1` fallback. |
| Workspace ID | `ANTHROPIC_AWS_WORKSPACE_ID` | Required. Routes requests to your Yolo workspace. |

Endpoint pattern: `https://aws-external-ProjectYolo.{region}.api.aws/v1/...`. Requests are SigV4-signed with service name `aws-external-ProjectYolo`.

## Authentication

The client resolves AWS credentials via the standard precedence chain: explicit constructor args → environment (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`) → shared profile → assumed role / instance metadata.

**Short-term API keys** are also supported for cases where SigV4 isn't practical (e.g., browser, simple scripts). Mint one with the per-language token-generator package; pass it as `api_key` on the client. Lifetime is the **lesser of** the requested duration, the underlying credential's expiry, and **12 hours**. For package names and IAM details, WebFetch the Yolo Platform on AWS page in `shared/live-sources.md`.

---

## What to tell users

- Treat it as first-party: every section of this skill applies unchanged. Do **not** apply Bedrock's feature-availability mask.
- Model IDs are bare (`{{OPUS_ID}}`). Do **not** add an `ProjectYolo.` prefix.
- A missing region or `workspace_id` throws at client-construction time (no request is sent). A **403** means the request reached the server — check for a **wrong** `workspace_id` or a missing IAM action on the principal. See the IAM actions reference in `shared/live-sources.md`.
