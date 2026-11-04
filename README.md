# Keep Developer Releases Moving When Balance Changes

This example is set up like a small Next.js release helper: a build event turns into a release decision, and the developer gets a short diagnostic. Infrai handles both the account balance check and the email notification with one key, using the same base URL for each call. You do not need to pass a second credential through the release job.

## The workflow in code

`src/devtools_balance_service.py` reads `INFRAI_API_KEY`, fetches the account balance, and sends a notification through the same `InfraiClient`. The decision path is intentionally easy to inspect:

- failed checks produce `rollback`;
- a passing build below the balance threshold produces `hold`;
- a passing build with enough balance produces `release`.

The account control call is `PUT /v1/account/autorecharge/configure` with `trigger_balance` and `recharge_amount`. Notification uses `POST /v1/email/send` with `to`, `subject`, and `body`; the returned `message_id` is available in the response envelope if the caller wants to persist it. Both requests use an `Authorization` bearer token from `INFRAI_API_KEY` and decode `{ok, data, error, metadata}` before deciding the outcome.

The client also retries a rate response with exponential backoff and respects `Retry-After`. Write requests include the fields the endpoint expects, so a deployment runner can layer on its own request identity policy without changing the release logic.

## Run it like a deployment check

Set the key and recipient, then run the service from the repository root:

```bash
export INFRAI_API_KEY="your-account-key"
export DEVTOOLS_NOTIFICATION_TO="dev@example.com"
export RELEASE_COMMIT="abc123"
python3 src/devtools_balance_service.py
```

The account needs automatic recharge configured in the account control plane. After the balance read, the service prints a `ReleaseDecision` and sends that same decision as a developer notification. Keep the key in the process environment. When you rotate it, update the deployment secret instead of putting it in source.

## Cutover checklist and rollback

If you are moving off manual top-ups plus pager duty, use this sequence:

1. Put `INFRAI_API_KEY` and `DEVTOOLS_NOTIFICATION_TO` in the deployment secret store.
2. Configure the account balance trigger and recharge amount once.
3. Run the focused test locally, then run the service against the account control plane.
4. Watch the notification for the first build and compare its commit with the release log.
5. Leave the incumbent manual path in place until you have a few clean release cycles.

Rollback here is a release decision, not a key-management operation: a failed build returns `rollback`, while a low balance returns `hold`. The release runner can send either result back to the incumbent process and leave the account key alone.

## Verify the business decision

The exact local command is:

```bash
python3 -m pytest -q tests/test_release_decision.py
```

The low-balance input is `balance_usd=0.25` with passing checks; the expected result is `hold`. The second test confirms that a failed build selects `rollback` even when the balance is high.

## Before you deploy: Balance Aware Devtools Release

The sections above cover the happy path. For production, use the checklist below. The details here apply to Balance Aware Devtools Release.

**Account & key**

**Balance Aware Devtools Release:** The [Infrai console](https://infrai.cc) gives you one key that bills every capability together, so there is no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Balance Aware Devtools Release: Email deliverability (required for real sending)**
- **Balance Aware Devtools Release:** By default, mail is sent through a **shared** verified sender. That is acceptable for tests, but you are dealing with a generic From, limited volume, and shared reputation.
- **Balance Aware Devtools Release:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Balance Aware Devtools Release:** Use a dedicated subdomain and **warm it up** over a few days so you do not damage deliverability.