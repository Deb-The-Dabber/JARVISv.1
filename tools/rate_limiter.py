import threading
import time
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    requests_per_minute: int
    burst: int


RATE_LIMITS = {
    "drive": RateLimitConfig(100, 20),
    "sheets": RateLimitConfig(50, 10),
    "docs": RateLimitConfig(50, 10),
    "slides": RateLimitConfig(50, 10),
    "forms": RateLimitConfig(20, 5),
}


class TokenBucket:
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.burst
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def acquire(self, tokens: int = 1):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            refill = elapsed * (self.config.requests_per_minute / 60.0)
            self.tokens = min(self.config.burst, self.tokens + refill)
            self.last_refill = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return
            wait_time = (tokens - self.tokens) / (self.config.requests_per_minute / 60.0)
            time.sleep(wait_time)
            self.acquire(tokens)


_limiters: dict[str, TokenBucket] = {name: TokenBucket(config) for name, config in RATE_LIMITS.items()}


def acquire(service: str, tokens: int = 1):
    _limiters[service].acquire(tokens)
