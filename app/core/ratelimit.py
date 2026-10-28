"""
Rate limiting for the endpoints that are worth attacking.

Three distinct problems, one mechanism:

* **Login** can be brute-forced. Without a limit, a password is guessable at
  machine speed and nothing slows it down.
* **Forgot-password and registration** send mail to any address given to them,
  so they can be pointed at someone to bombard their inbox.
* Those same endpoints spend the platform's daily email quota. Exhausting it
  costs an attacker nothing and stops legitimate students signing up, which is
  a denial of service with no packets flooded.

Deliberately an in-process fixed-window counter rather than Redis. The API runs
as a single instance; adding a datastore to defend a service this size would be
more moving parts than the problem justifies. If it is ever scaled to several
workers this needs to move to shared state — the docstring is here so that is a
decision rather than a surprise.
"""

import threading
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status

from app.core.config import settings

# The integration suite signs the same accounts in dozens of times, which any
# sane login limit would block. Enforcement is therefore off under test and the
# rate-limit tests switch it back on for themselves — so the limits are still
# covered, without every other test having to care.
ENFORCE_IN_TESTS = False


@dataclass
class Rule:
    """`limit` requests per `window` seconds."""

    limit: int
    window: int


# Tuned to be invisible to a real person and painful to a script. A student
# mistyping their password four times in a minute is normal; forty is not.
LOGIN = Rule(limit=8, window=60)
REGISTER = Rule(limit=5, window=600)
EMAIL_SEND = Rule(limit=4, window=3600)


@dataclass
class _Window:
    count: int = 0
    started: float = field(default_factory=time.monotonic)


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, _Window] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float) -> None:
        """
        Drops expired windows so a long-running process does not accumulate a
        bucket per address forever. Cheap, and only every few minutes.
        """
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        stale = [k for k, w in self._buckets.items() if now - w.started > 3600]
        for key in stale:
            del self._buckets[key]

    def check(self, key: str, rule: Rule) -> int | None:
        """
        Records a hit. Returns None when allowed, or the seconds to wait when
        the caller has gone over.
        """
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            window = self._buckets.get(key)

            if window is None or now - window.started >= rule.window:
                self._buckets[key] = _Window(count=1, started=now)
                return None

            window.count += 1
            if window.count > rule.limit:
                return max(1, int(rule.window - (now - window.started)))
            return None

    def reset(self, key: str) -> None:
        """Clears a bucket — used after a successful login."""
        with self._lock:
            self._buckets.pop(key, None)


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """
    The caller's address, honouring the proxy header.

    `X-Forwarded-For` is only trustworthy because the API sits behind our own
    reverse proxy in production. Exposed directly to the internet this would be
    spoofable and the limit would be trivially bypassed — so do not do that.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, rule: Rule, *, scope: str, identifier: str = "") -> None:
    """
    Applies `rule` and raises 429 when exceeded.

    `identifier` narrows the bucket beyond the IP — an email address, usually —
    so one person hammering one account does not lock out everyone else behind
    the same office NAT.
    """
    if settings.ENVIRONMENT == "test" and not ENFORCE_IN_TESTS:
        return

    key = f"{scope}:{client_ip(request)}:{identifier.lower()}"
    retry_after = limiter.check(key, rule)
    if retry_after is None:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many attempts. Please wait a moment and try again.",
        headers={"Retry-After": str(retry_after)},
    )


def clear(request: Request, *, scope: str, identifier: str = "") -> None:
    limiter.reset(f"{scope}:{client_ip(request)}:{identifier.lower()}")
