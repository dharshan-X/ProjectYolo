from enum import Enum
from dataclasses import dataclass

class FailoverReason(Enum):
    RATE_LIMIT = "rate_limit"
    CONTEXT_OVERFLOW = "context_overflow"
    IMAGE_TOO_LARGE = "image_too_large"
    AUTH_FAILURE = "auth_failure"
    OVERLOADED = "overloaded"
    NETWORK_ERROR = "network_error"
    CONTENT_POLICY = "content_policy"
    UNKNOWN = "unknown"

@dataclass
class ClassifiedError:
    reason: FailoverReason
    original_error: str
    retryable: bool
    recommended_delay: float

def classify_api_error(error: Exception) -> ClassifiedError:
    err_msg = str(error).lower()
    
    # Context Overflow
    if any(x in err_msg for x in ["context_length_exceeded", "maximum context length", "too many tokens"]):
        return ClassifiedError(FailoverReason.CONTEXT_OVERFLOW, err_msg, True, 0.0)
        
    # Rate Limits
    if any(x in err_msg for x in ["429", "rate limit", "too many requests"]):
        return ClassifiedError(FailoverReason.RATE_LIMIT, err_msg, True, 2.0)
        
    # Server Overloaded / Gateway errors
    if any(x in err_msg for x in ["500", "502", "503", "504", "overloaded", "server error"]):
        return ClassifiedError(FailoverReason.OVERLOADED, err_msg, True, 3.0)
        
    # Image constraints
    if any(x in err_msg for x in ["image_too_large", "payload too large", "413"]):
        return ClassifiedError(FailoverReason.IMAGE_TOO_LARGE, err_msg, True, 0.0)
        
    # Auth Failures
    if any(x in err_msg for x in ["401", "403", "invalid_api_key", "unauthorized", "invalid api key"]):
        return ClassifiedError(FailoverReason.AUTH_FAILURE, err_msg, False, 0.0)
        
    # Content Policy Block
    if any(x in err_msg for x in ["content_policy_violation", "blocked", "safety"]):
        return ClassifiedError(FailoverReason.CONTENT_POLICY, err_msg, False, 0.0)
        
    # Network / Connection Issues
    if any(x in err_msg for x in [
        "peer closed", "incomplete chunked read", "connection reset",
        "remote protocol error", "connection closed", "readtimeout",
        "timeout", "network", "socket"
    ]):
        return ClassifiedError(FailoverReason.NETWORK_ERROR, err_msg, True, 1.0)
        
    return ClassifiedError(FailoverReason.UNKNOWN, err_msg, False, 0.0)
