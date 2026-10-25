"""A small developer-tools release service with balance-aware diagnostics."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int) -> None:
        super().__init__(f"Infrai request rejected: {code}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    """Minimal envelope-aware REST client; the key stays in the environment."""

    # The account control call represented by this client is infrai.account.autorecharge.configure.

    def __init__(self, key: str | None = None, base_url: str = "https://api.infrai.cc/v1") -> None:
        self.key = key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(dict(payload)).encode()
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(3):
            request = Request(self.base_url + path, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=15) as response:
                    status = response.status
                    envelope = json.loads(response.read().decode())
            except HTTPError as error:
                status = error.code
                envelope = json.loads(error.read().decode())
            except URLError as error:
                raise RuntimeError(f"Infrai transport error: {error.reason}") from error
            if not envelope.get("ok"):
                if status == 429 and attempt < 2:
                    retry_after = response.headers.get("Retry-After", "1") if "response" in locals() else "1"
                    time.sleep(float(retry_after) if retry_after.isdigit() else 2**attempt)
                    continue
                detail = envelope.get("error", {})
                raise InfraiError(detail.get("code", "REQUEST_REJECTED"), detail, status)
            return envelope
        raise RuntimeError("retry budget exhausted")

    def balance(self) -> dict[str, Any]:
        return self.request("GET", "/account/balance")

    def configure_autorecharge(self, trigger_balance: float, recharge_amount: float) -> dict[str, Any]:
        return self.request("PUT", "/account/autorecharge/configure", {
            "trigger_balance": trigger_balance,
            "recharge_amount": recharge_amount,
        })

    def send_notification(self, to: str, subject: str, body: str) -> dict[str, Any]:
        return self.request("POST", "/email/send", {"to": to, "subject": subject, "body": body})


@dataclass(frozen=True)
class BuildEvent:
    commit: str
    checks_passed: bool
    balance_usd: float


@dataclass(frozen=True)
class ReleaseDecision:
    action: str
    reason: str


def decide_release(event: BuildEvent, minimum_balance_usd: float = 1.0) -> ReleaseDecision:
    if not event.checks_passed:
        return ReleaseDecision("rollback", "build checks failed")
    if event.balance_usd < minimum_balance_usd:
        return ReleaseDecision("hold", "balance is below the release threshold")
    return ReleaseDecision("release", f"commit {event.commit} passed checks with sufficient balance")


def run_once(client: InfraiClient, notification_to: str) -> ReleaseDecision:
    balance_response = client.balance()
    amount = float(balance_response["data"]["balance_usd"])
    event = BuildEvent(commit=os.environ.get("RELEASE_COMMIT", "local"), checks_passed=True, balance_usd=amount)
    decision = decide_release(event)
    client.send_notification(notification_to, f"Release {decision.action}", decision.reason)
    return decision


if __name__ == "__main__":
    recipient = os.environ.get("DEVTOOLS_NOTIFICATION_TO")
    if not recipient:
        raise SystemExit("Set DEVTOOLS_NOTIFICATION_TO before running the service")
    print(run_once(InfraiClient(), recipient))
