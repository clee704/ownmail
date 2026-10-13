# iPhone Home Screen validation

Use this runbook for the remaining physical-device checks in
[TASK-50](../backlog/tasks/task-50%20-%20Improve-the-iPhone-Home-Screen-web-app-experience.md).
Record observations against the exact tested commit. Browser tests, responsive
emulation and an iPhone simulator provide supporting evidence; they do not
complete the physical-iPhone checks.

## Prerequisites and inputs

- A physical iPhone, with permission to install and operate the Home Screen app.
  Record its model, iOS version, Safari version if available, and test date.
- A clean checkout of the build under test. Record `git rev-parse HEAD` and
  `git status --short`; verify the running server uses that checkout.
- An already authorized, phone-reachable origin serving only the synthetic
  archive below. Record its scheme and whether HTTPS is trusted on the phone.
  Keep private hostnames, addresses and deployment details in local operator
  notes. This procedure does not authorize exposing a server, configuring HTTPS,
  changing network/security settings or requesting device permissions.
- The normal Python environment and existing web sanitizer dependencies from
  [development setup](../CONTRIBUTING.md#development-setup). The device server
  must use the real sanitizer. Pytest fixtures mock application components and
  are unsuitable for a device server; never substitute a passthrough sanitizer.
- An authorized way to interrupt and restore connectivity to this isolated
  server. A held-response test needs an approved diagnostic facility; record
  that check as blocked if one is unavailable.

Per run, retain the commit, device/software versions, origin scheme/trust, fresh
fixture directory, page size, chosen message numbers, paragraph position,
background duration, interruption method and observed failure time. Use a new
fixture directory for each run. Do not copy personal configuration, archives,
source settings or credentials into it.

## Prepare an isolated archive

From the checkout, activate its existing Python environment and run this block.
It uses the standard library to create 45 numbered messages and one long HTML
message, then imports them through the existing CLI. Both the explicit config
and archive argument point to newly created temporary data. No source or
credential setup is needed; import copies the generated inputs.

```sh
python - <<'PY'
import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix="ownmail-home-screen-"))
inputs = root / "inputs"
inputs.mkdir()
archive = root / "archive"
config = root / "config.yaml"
config.write_text(json.dumps({
    "archive_root": str(archive),
    "sources": [],
    "web": {
        "brand_name": "Archive validation",
        "page_size": 20,
        "block_images": True,
    },
}, indent=2) + "\n", encoding="utf-8")

for number in range(1, 47):
    message = EmailMessage()
    message["From"] = "Fixture Sender <sender@example.test>"
    message["To"] = "Fixture Reader <reader@example.test>"
    message["Date"] = format_datetime(
        datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=number)
    )
    message["Message-ID"] = f"<home-screen-{number:03d}@example.test>"
    message["Subject"] = f"Home Screen fixture {number:03d}"
    message.set_content(f"Synthetic message {number:03d} for navigation checks.\n")
    if number == 46:
        message.replace_header("Subject", "Home Screen fixture 046 long HTML")
        paragraphs = "".join(
            f"<p>Paragraph {paragraph:03d}: synthetic reading-position marker. "
            "Scroll, resume and rotate here.</p>"
            for paragraph in range(1, 301)
        )
        message.add_alternative(
            "<!doctype html><html><body><h1>Long synthetic message</h1>"
            + paragraphs + "<p>END OF MESSAGE</p></body></html>",
            subtype="html",
        )
    (inputs / f"message-{number:03d}.eml").write_bytes(
        message.as_bytes(policy=SMTP)
    )

subprocess.run([
    sys.executable, "-m", "ownmail", "--config", str(config),
    "--archive-root", str(archive), "import", str(inputs),
], check=True)
with sqlite3.connect(archive / "ownmail.db") as database:
    assert database.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 46
assert len(list(inputs.glob("*.eml"))) == 46
print(f"Fixture directory: {root}")
print(f"Explicit config: {config}")
print("Expected: 46 messages; page size 20; no configured sources.")
PY
```

The JSON-formatted config is valid YAML. Preserve its explicit `archive_root`
and empty `sources` when the authorized operator connects this fixture to the
existing deployment. Apply only the already approved host/origin settings;
refer to [allowed hosts](setup.md#allowed-hosts) and
[CSRF protection](setup.md#cross-site-request-protection) for configuration
semantics. This preparation block does not start a server. Confirm the deployed
UI shows only the numbered fixtures before continuing. A wrong Host yields 400;
a disallowed origin or expired page token can yield 403. Distinguish these from
connection loss.

## Manual checks

Record pass, fail or blocked for each check, with the actual behavior and any
synthetic screenshot or request-log evidence. Avoid personal screens and URLs
in public task notes.

1. **Install and cold launch.** Open the authorized origin in Safari, add it to
   the Home Screen, then launch its icon. Record the installed name/icon and
   whether it opens without Safari chrome. Confirm launch reaches `/search`
   and internal list, reader and settings navigation stays in the app. Check
   light/dark theme colors and readable status-bar content. Record a fresh
   launch separately from returning to a backgrounded app.
2. **List, reader and Back.** Search `Home Screen`, select date ascending sort,
   go to page 2 and scroll to a numbered row. Record query, sort, page, top
   visible row and scroll position. Open that row and use Back to results;
   repeat using the native Back gesture/history where available. Confirm the
   same result state and position return without a toolbar jump or keyboard
   opening unexpectedly. With a hardware keyboard, open a focused row and
   activate Back to results using the keyboard; check row focus restoration.
   Record touch and keyboard results separately.
3. **Long message and resume.** Open fixture 046 and scroll to paragraph 150.
   Record the visible marker, background the app for a recorded interval, then
   return. Repeat after locking/unlocking the phone. Reload the same unchanged
   reader through an available native reload control, or record reload as
   blocked if unavailable. Confirm the view and reading position remain useful.
   Scroll to paragraph 300 and END OF MESSAGE; check for clipping. A list
   launch must remain a list rather than reopen the remembered reader.
4. **Stale and missing reader.** While the long reader is backgrounded, have
   the authorized fixture operator change only that synthetic archived file's
   modification time (`Path.touch()` on its verified fixture path). Reload the
   reader and confirm the previous app-saved offset is not applied to the
   changed file version. Native history restoration can preserve position;
   record that separately. At the same origin open
   `/email/000000000000000000000000?return_to=%2Fsearch%3Fq%3DHome%2BScreen`.
   Confirm Message unavailable offers a usable Back to results link. No email
   deletion is needed for this missing-message check.
5. **Keyboard and orientation.** Focus search, type, clear and submit a query.
   Check controls with the software keyboard open and after dismissal. Rotate
   list and long-reader views through portrait and both landscape orientations.
   Check the status bar, cutout, home indicator, menus, search and Back controls
   for overlap, clipping and accidental horizontal scrolling. Repeat a brief
   desktop keyboard/navigation check against the same build and fixture.
6. **Navigation interruption.** Start from a loaded page, interrupt the approved
   connection and navigate to another numbered message. Record whether failure
   is immediate, the browser replaces the page, or a held request reaches the
   30-second app deadline. When the app page remains loaded, verify pending
   feedback ends and Retry is usable. Restore connectivity and select Retry;
   it should open the requested destination. Check a second destination owns
   Retry if navigation changes while the first request is pending. Use the
   approved held-response facility for the deadline case; immediate refusal
   alone does not verify the deadline.
7. **Unconfirmed action.** On a loaded synthetic reader, open Edit labels,
   prepare a distinctive synthetic label, interrupt the connection and Save
   labels. Check bounded pending feedback, re-enabled controls and absence of
   false success. Restore connectivity and select Retry. It reloads the current
   page; inspect saved labels before deliberately repeating Save. If approved
   request logs are available, confirm Retry made no label mutation request.
   A lost response can follow a committed change. Use a held/lost-response case
   when authorized; otherwise mark that portion blocked. Repeat interruption
   while loading the label editor to check its loading feedback terminates.
8. **Unavailable cold launch.** With the server unreachable through the approved
   interruption method, close the app and launch its Home Screen icon. Record
   the browser connection-error screen, then restore connectivity and recover.
   There is currently no app-provided cold-launch offline fallback. No service
   worker or offline archive is installed. A future static app-shell and
   reconnection fallback requires trusted HTTPS for phone/LAN access; the
   localhost exception does not cover a LAN address. Private messages, search
   results and attachments are outside that proposed cache scope.

The current reader directly embeds sanitized HTML.
[TASK-142](../backlog/tasks/task-142%20-%20Render-reader-messages-in-a-sandboxed-frame.md)
has not landed: do not claim frame isolation or frame-specific device checks
from this run. If the tested revision changes the reader, update this procedure
before attributing its results to TASK-50.

## Supplemental simulator checks

When simulator access is authorized, use the installed Xcode simulator
management UI (DeviceHub in Xcode 27) to select and boot an available iPhone
runtime. Record Xcode, simulator model and iOS runtime versions. A standalone
Simulator app may be absent; verify the installed UI instead of assuming its
location.

Use the same synthetic fixture. When a local server is authorized, set these
`TASK50_CONFIG` and `TASK50_ARCHIVE` to the fixture paths printed above, and
`TASK50_PORT` to an unused local port. Set `TASK50_LOG` to a local evidence file.
Run from the activated checkout environment:

```sh
python -u -m ownmail --config "$TASK50_CONFIG" --archive-root "$TASK50_ARCHIVE" serve --host 127.0.0.1 --port "$TASK50_PORT" --no-browser > "$TASK50_LOG" 2>&1
```

Keep the loopback binding. Inspect the log to confirm the printed archive,
page size and allowed hosts, and verify the real sanitizer starts. Open the
printed loopback URL in simulated Safari, add it to the Home Screen and repeat
the available manual checks. Capture simulator results separately, including
unsupported keyboard, lock/resume, orientation or connectivity checks. If
loopback access fails, record the failure before considering any network
change. Simulator evidence does not establish physical cutout, touch, keyboard,
background/resume or Home Screen acceptance.

With Codex computer controls, select DeviceHub by its installed app path. Enable
Capture Keyboard and focus the simulated screen before typing; otherwise keys
can reach the host sidebar. Web content may lack accessibility elements, so
use a fresh screenshot for coordinates. Observe again after scrolling settles;
an immediate screenshot can show a transient blank page or the old position.
Captured Page Down and a drag within the message both moved the reader in the
iOS 26.5 run. After testing, stop the server started for this run and shut down
the selected simulator if it was initially shut down.
Retain the server log when checking mutation replay; an interactive tool session
can disappear after an agent handoff. Compare mutation requests before and after
Retry, including any explicitly rejected CSRF request.

## Results template

```text
Date:
Exact commit / clean checkout / deployed revision confirmed:
iPhone model / iOS / Safari version if available:
Origin scheme / trusted HTTPS (private endpoint retained locally):
Fixture recipe version (runbook commit) / page size / source-free confirmed:
Chosen row / paragraph marker / background intervals:
Interruption method / held-response facility:

Check                         Pass / fail / blocked   Observation / evidence
Install and online cold launch
List, reader and Back (touch)
List focus and desktop keyboard
Long reader, background and lock/resume
Same-message reload
Changed-version and missing-reader recovery
Software keyboard and portrait/landscape
Interrupted navigation and deadline
Unconfirmed action and Retry without replay
Label-loading interruption
Unavailable cold launch and recovery

Supporting simulator/browser evidence (separate from physical checks):
Failures, blocked portions and next action:
```

Summarize device observations in TASK-50 without private deployment details.
Keep incomplete checks open; a fixture import or passing desktop gate supplies
no physical-device evidence. Retain the disposable fixture until results are
recorded; any cleanup must target only the verified directory created by this
run.
