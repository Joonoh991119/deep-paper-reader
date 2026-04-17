# Sprint 10 — Paste this as the FIRST message in the new session

Copy everything inside the fenced block below and paste it as your first message
in the fresh Claude Code session at 2026-04-17 21:00 KST. The new session reads
the mission doc and begins autonomous execution.

```
/loop

You are running Sprint 10 — the Paper-RAG pipeline. This is an autonomous 12-hour session starting now (2026-04-17 21:00 KST, ending by 2026-04-18 09:00 KST).

BEFORE ANYTHING ELSE, read these two files in order and follow them literally:

1. /Users/joonoh/deep-paper-reader/docs/sprint10/MISSION.md
2. /Users/joonoh/deep-paper-reader/.sprint10/checkpoint.json

Then execute bash /Users/joonoh/deep-paper-reader/scripts/sprint10-env-check.sh and paste its output into .sprint10/session-log.md.

Work from the repo root: /Users/joonoh/deep-paper-reader.

Self-pace via ScheduleWakeup. On rate limit or crash, follow the rate-limit protocol in MISSION.md section "Rate-limit protocol". Do NOT ask me to confirm steps — the mission doc is the contract. Only stop and Slack-DM me if you are truly blocked (blocked:true in checkpoint).

Your first concrete action is Phase 0 in the mission doc.
```

---

## Kickoff one-liner (run in a Terminal tab at 9pm)

```sh
caffeinate -dis -w $$ claude
```

Then paste the fenced block above as the first message.

- `caffeinate -dis -w $$` prevents display/system/idle sleep for as long as the current shell (`$$`) stays alive. Close the tab → caffeinate releases.
- If you want it to survive an accidental tab close, use `tmux` or `screen`:
  ```sh
  tmux new -s sprint10
  caffeinate -dis -w $$ claude
  ```
  Detach with `Ctrl-b d`, reattach with `tmux a -t sprint10`.

## After kickoff

- Check progress around 2am and 6am via `cat ~/deep-paper-reader/.sprint10/session-log.md`.
- Slack DM will arrive from csnl-slack-bot when Sprint 10 finishes (or if blocked).
- The session will also push commits to GitHub — `gh pr list --repo Joonoh991119/deep-paper-reader` will show the final PR.
