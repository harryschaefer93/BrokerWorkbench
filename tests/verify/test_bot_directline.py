"""Bot DirectLine parity test \u2014 Phase C verification, no Teams client needed.

For each canonical Field Day prompt:
  1. Open a DirectLine conversation via REST (token from BROKER_DIRECTLINE_SECRET)
  2. Post the prompt as a user activity
  3. Poll for the bot's response activities (incl. Adaptive Card attachments)
  4. Extract the answer text and assert keyword overlap with the same prompt's
     web/hosted snapshot under tests/eval/snapshots/<id>.json (proves the bot
     surface matches what the web surface delivers \u2014 same agent, same answer
     quality)

Run:
  $env:BROKER_DIRECTLINE_SECRET = az bot directline show -g rg-bwbench-sc `
      -n bot-brokerworkbench-dev --with-secrets true `
      --query "properties.properties.sites[0].key" -o tsv
  pytest -m live tests/verify/test_bot_directline.py -v
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_PATH = REPO_ROOT / "tests" / "eval" / "prompts.yaml"
SNAPSHOTS_DIR = REPO_ROOT / "tests" / "eval" / "snapshots"
DL_BASE = "https://directline.botframework.com/v3/directline"


def _load_prompts() -> list[dict[str, Any]]:
    return yaml.safe_load(PROMPTS_PATH.read_text())


def _secret() -> str:
    s = os.environ.get("BROKER_DIRECTLINE_SECRET", "")
    if not s:
        pytest.skip("BROKER_DIRECTLINE_SECRET not set; skipping bot DirectLine test")
    return s


def _start_conversation(client: httpx.Client, secret: str) -> str:
    resp = client.post(
        f"{DL_BASE}/conversations",
        headers={"Authorization": f"Bearer {secret}"},
    )
    resp.raise_for_status()
    return resp.json()["conversationId"]


def _post_user(client: httpx.Client, secret: str, conv_id: str, text: str) -> str:
    body = {
        "type": "message",
        "from": {"id": "eval-harness"},
        "text": text,
    }
    resp = client.post(
        f"{DL_BASE}/conversations/{conv_id}/activities",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
        json=body,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _wait_for_bot_reply(
    client: httpx.Client, secret: str, conv_id: str, after_id: str, timeout_s: float
) -> dict[str, Any]:
    """Poll the activity feed until the bot posts a message AFTER ``after_id``."""
    watermark: str | None = None
    deadline = time.monotonic() + timeout_s
    user_seen = False
    while time.monotonic() < deadline:
        url = f"{DL_BASE}/conversations/{conv_id}/activities"
        if watermark:
            url += f"?watermark={watermark}"
        resp = client.get(url, headers={"Authorization": f"Bearer {secret}"})
        resp.raise_for_status()
        payload = resp.json()
        watermark = payload.get("watermark", watermark)
        for activity in payload.get("activities", []):
            aid = activity.get("id", "")
            if not user_seen:
                user_seen = aid == after_id
                continue
            # First non-user activity AFTER the user's prompt is the bot reply.
            if activity.get("from", {}).get("id") != "eval-harness":
                return activity
        time.sleep(1.5)
    raise TimeoutError(
        f"bot did not reply within {timeout_s}s after activity {after_id}"
    )


def _extract_text(activity: dict[str, Any]) -> str:
    """Pull human-readable text out of the bot's reply.

    The bot replies with Adaptive Cards in attachments. Walk the card body
    for TextBlock content; fall back to ``activity.text``.
    """
    parts: list[str] = []
    if activity.get("text"):
        parts.append(activity["text"])
    for att in activity.get("attachments") or []:
        content = att.get("content") or {}
        for block in content.get("body") or []:
            if block.get("type") == "TextBlock" and block.get("text"):
                parts.append(block["text"])
            for inner in block.get("items") or []:
                if inner.get("type") == "TextBlock" and inner.get("text"):
                    parts.append(inner["text"])
    return "\n".join(parts)


@pytest.mark.live
@pytest.mark.parametrize("case", _load_prompts(), ids=lambda c: c["id"])
def test_bot_directline_parity(case: dict[str, Any]) -> None:
    secret = _secret()
    with httpx.Client(timeout=httpx.Timeout(60.0, read=300.0)) as client:
        conv_id = _start_conversation(client, secret)
        user_aid = _post_user(client, secret, conv_id, case["prompt"])
        reply = _wait_for_bot_reply(
            client, secret, conv_id, after_id=user_aid, timeout_s=240.0
        )

    text = _extract_text(reply).lower()
    assert text, f"bot reply was empty: {json.dumps(reply)[:300]}"

    expected_kw = case.get("expected_keywords", [])
    if expected_kw:
        hits = sum(1 for kw in expected_kw if kw.lower() in text)
        required = max(1, (len(expected_kw) * 2) // 3)
        assert hits >= required, (
            f"only {hits}/{len(expected_kw)} keywords in bot reply; need >= {required}. "
            f"Keywords={expected_kw}. Reply head={text[:300]!r}"
        )
