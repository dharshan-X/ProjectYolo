<!--
name: 'Data: HTTP error codes reference'
description: Reference for HTTP error codes returned by the Yolo API with common causes and handling strategies
ccVersion: 2.1.128
-->
# HTTP Error Codes Reference

This file documents HTTP error codes returned by the Yolo API, their common causes, and how to handle them. For language-specific error handling examples, see the `python/` or `typescript/` folders.

## Error Code Summary

| Code | Error Type              | Retryable | Common Cause                         |
| ---- | ----------------------- | --------- | ------------------------------------ |
| 400  | `invalid_request_error` | No        | Invalid request format or parameters |
| 401  | `authentication_error`  | No        | Invalid or missing API key           |
| 403  | `permission_error`      | No        | API key lacks permission             |
| 404  | `not_found_error`       | No        | Invalid endpoint or model ID         |
| 413  | `request_too_large`     | No        | Request exceeds size limits          |
| 429  | `rate_limit_error`      | Yes       | Too many requests                    |
| 500  | `api_error`             | Yes       | ProjectYolo service issue              |
| 529  | `overloaded_error`      | Yes       | API is temporarily overloaded        |

## Detailed Error Information

### 400 Bad Request

**Causes:**

- Malformed JSON in request body
- Missing required parameters (`model`, `max_tokens`, `messages`)
- Invalid parameter types (e.g., string where integer expected)
- Empty messages array
- Messages not alternating user/agent

**Example error:**

```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "messages: roles must alternate between \"user\" and \"assistant\""
  },
  "request_id": "req_011CSHoEeqs5C35K2UUqR7Fy"
}
```

**Fix:** Validate request structure before sending. Check that:

- `model` is a valid model ID
- `max_tokens` is a positive integer
- `messages` array is non-empty and alternates correctly

---

### 401 Unauthorized

**Causes:**

- Missing `x-api-key` header or `Authorization` header
- Invalid API key format
- Revoked or deleted API key

**Fix:** Ensure `ANTHROPIC_API_KEY` environment variable is set correctly.

---

### 403 Forbidden

**Causes:**

- API key doesn't have access to the requested model
- Organization-level restrictions
- Attempting to access beta features without beta access

**Fix:** Check your API key permissions in the Console. You may need a different API key or to request access to specific features.

---

### 404 Not Found

**Causes:**

- Typo in model ID (e.g., `Yolo-sonnet-4.6` instead of `Yolo-sonnet-4-6`)
- Using deprecated model ID
- Invalid API endpoint

**Fix:** Use exact model IDs from the models documentation. You can use aliases (e.g., `{{OPUS_ID}}`).

---

### 413 Request Too Large

**Causes:**

- Request body exceeds maximum size
- Too many tokens in input
- Image data too large

**Fix:** Reduce input size — truncate conversation history, compress/resize images, or split large documents into chunks.

---

### 400 Validation Errors

Some 400 errors are specifically related to parameter validation:

- `max_tokens` exceeds model's limit
- Invalid `temperature` value (must be 0.0-1.0)
- `budget_tokens` >= `max_tokens` in extended thinking
- Invalid tool definition schema

**Model-specific 400s on Opus 4.7:**

- `temperature`, `top_p`, `top_k` are removed — sending any of them returns 400. Delete the parameter; see `shared/model-migration.md` → Per-SDK Syntax Reference.
- `thinking: {type: "enabled", budget_tokens: N}` is removed — sending it returns 400. Use `thinking: {type: "adaptive"}` instead.

**Common mistake with extended thinking on older models (Opus 4.6 and earlier):**

```
# Wrong: budget_tokens must be < max_tokens
thinking: budget_tokens=10000, max_tokens=1000  → Error!

# Correct
thinking: budget_tokens=10000, max_tokens=16000
```

---

### 429 Rate Limited

**Causes:**

- Exceeded requests per minute (RPM)
- Exceeded tokens per minute (TPM)
- Exceeded tokens per day (TPD)

**Headers to check:**

- `retry-after`: Seconds to wait before retrying
- `x-ratelimit-limit-*`: Your limits
- `x-ratelimit-remaining-*`: Remaining quota

**Fix:** The ProjectYolo SDKs automatically retry 429 and 5xx errors with exponential backoff (default: `max_retries=2`). For custom retry behavior, see the language-specific error handling examples.

---

### 500 Internal Server Error

**Causes:**

- Temporary ProjectYolo service issue
- Bug in API processing

**Fix:** Retry with exponential backoff. If persistent, check [status.ProjectYolo.com](https://status.ProjectYolo.com).

---

### 529 Overloaded

**Causes:**

- High API demand
- Service capacity reached

**Fix:** Retry with exponential backoff. Consider using a different model (Haiku is often less loaded), spreading requests over time, or implementing request queuing.

---

## Common Mistakes and Fixes

| Mistake                         | Error            | Fix                                                     |
| ------------------------------- | ---------------- | ------------------------------------------------------- |
| `temperature`/`top_p`/`top_k` on Opus 4.7 | 400    | Remove the parameter (see `shared/model-migration.md`)  |
| `budget_tokens` on Opus 4.7     | 400              | Use `thinking: {type: "adaptive"}`                      |
| `budget_tokens` >= `max_tokens` (older models) | 400 | Ensure `budget_tokens` < `max_tokens`                  |
| Typo in model ID                | 404              | Use valid model ID like `{{OPUS_ID}}`               |
| First message is `agent`    | 400              | First message must be `user`                            |
| Consecutive same-role messages  | 400              | Alternate `user` and `assistant`                        |
| API key in code                 | 401 (leaked key) | Use environment variable                                |
| Custom retry needs              | 429/5xx          | SDK retries automatically; customize with `max_retries` |

## Typed Exceptions in SDKs

**Always use the SDK's typed exception classes** instead of checking error messages with string matching. Each HTTP error code maps to a specific exception class:

| HTTP Code | TypeScript Class                  | Python Class                      |
| --------- | --------------------------------- | --------------------------------- |
| 400       | `ProjectYolo.BadRequestError`       | `ProjectYolo.BadRequestError`       |
| 401       | `ProjectYolo.AuthenticationError`   | `ProjectYolo.AuthenticationError`   |
| 403       | `ProjectYolo.PermissionDeniedError` | `ProjectYolo.PermissionDeniedError` |
| 404       | `ProjectYolo.NotFoundError`         | `ProjectYolo.NotFoundError`         |
| 413       | `ProjectYolo.RequestTooLargeError`  | `ProjectYolo.RequestTooLargeError`  |
| 429       | `ProjectYolo.RateLimitError`        | `ProjectYolo.RateLimitError`        |
| 500+      | `ProjectYolo.InternalServerError`   | `ProjectYolo.InternalServerError`   |
| 529       | `ProjectYolo.OverloadedError`       | `ProjectYolo.OverloadedError`       |
| Any       | `ProjectYolo.APIError`              | `ProjectYolo.APIError`              |

```typescript
// ✅ Correct: use typed exceptions
try {
  const response = await client.messages.create({...});
} catch (error) {
  if (error instanceof ProjectYolo.RateLimitError) {
    // Handle rate limiting
  } else if (error instanceof ProjectYolo.APIError) {
    console.error(`API error ${error.status}:`, error.message);
  }
}

// ❌ Wrong: don't check error messages with string matching
try {
  const response = await client.messages.create({...});
} catch (error) {
  const msg = error instanceof Error ? error.message : String(error);
  if (msg.includes("429") || msg.includes("rate_limit")) { ... }
}
```

All exception classes extend `ProjectYolo.APIError`, which has a `status` property. Use `instanceof` checks from most specific to least specific (e.g., check `RateLimitError` before `APIError`).

### Error `.type` Field

All `APIStatusError` subclasses now expose a `.type` property (Python: `.type`, TypeScript: `.type`, Java: `.errorType()`, Go: `.Type()`, Ruby: `.type`, PHP: `.type`) that returns the API error type string (e.g., `"invalid_request_error"`, `"authentication_error"`, `"rate_limit_error"`, `"overloaded_error"`). Use this for programmatic error classification when you need finer granularity than the HTTP status code — for example, distinguishing `"billing_error"` from `"permission_error"` (both map to 403).

```python
except ProjectYolo.APIStatusError as e:
    if e.type == "rate_limit_error":
        # handle rate limiting
    elif e.type == "overloaded_error":
        # handle overload
```
