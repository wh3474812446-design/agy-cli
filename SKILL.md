---
name: agy-cli
description: Run Google's Antigravity CLI (agy) non-interactively for scoped analysis, reviews, and authorized implementation, with resumable conversations and explicit result handling.
---

# Antigravity CLI

Use `scripts/agy-run.sh` for one non-interactive agy turn. Resolve it relative to this skill's directory. It requires Bash 4.4+, `jq`, and an installed, authenticated agy. It finds agy on `PATH`, then at `~/.local/bin/agy`; `AGY_BIN` selects an executable path. The wrapper does not install or authenticate agy.

## Invocation

```bash
/path/to/skill/scripts/agy-run.sh --cwd /path/to/project \
  'Explain the retry logic in src/client.ts and identify missing evidence.'
```

Supply one quoted positional prompt, `--prompt-file FILE`, or stdin. Use a quoted heredoc for multiline or shell-sensitive text; never insert untrusted task text into shell syntax. Use `--` before a positional prompt starting with `-`. Explicit prompt input takes precedence over stdin; positional and file input cannot be combined. Prompts, including the injected execution instruction, must be below 120,000 bytes because agy receives them as one argv element.

Without an explicit prompt, stdin is read only when it is a pipe or regular file (including heredocs). A missing prompt on an agent tool's open socket, character device, or TTY fails immediately with **64 / `usage_error`**. Use `--prompt-file -` to explicitly read a non-TTY stdin stream, including a socket. Accepted streams must reach EOF; prompt reading has no timeout, and `--timeout` applies only to agy.

A positional prompt over roughly **128KB** can be rejected by the OS before the script runs: Bash reports `Argument list too long` and exit **126**, with no wrapper metadata. Use `--prompt-file` or stdin for large prompts so the wrapper can validate them. These input methods still enforce the 120,000-byte budget; shorten oversized prompts or reference context files.

Set `--cwd` to the task workspace. Relative prompt, schema, and additional-directory paths resolve from the caller's original directory. Leave model and effort unset unless needed; discover IDs with the installed `agy models`. Explicit Claude models reject `--effort`.

Choose the write level to match the authorized task:

- `none` (default): requests plan mode and injects a no-edit/no-command instruction.
- `files`: requests accept-edits mode and prohibits shell commands in the prompt.
- `commands`: requests accept-edits mode and adds `--dangerously-skip-permissions`, auto-approving **all** tool permissions, not just shell commands.

All levels request `--sandbox`. These flags and prompt instructions are behavioral controls, not a verified filesystem boundary. Strict read-only requirements need external enforcement. Do not raise the write level just to bypass a denial; permission choices never expand task scope.

The default print timeout is **600s**. Set `--timeout DUR` for a different budget; `0` disables it. Schema, coding, and resumed turns can take several minutes. This is agy's print deadline, not a process watchdog or a guarantee that backend work stops. Let the calling tool keep the process alive and collect its final output.

## Output and follow-up

By default, stdout contains the response text and stderr contains one `agy-run: {...}` metadata line with outcome, exit codes, conversation ID, and any diagnostics. Use `--json` for one compact envelope on stdout, with the full parsed result (including usage and duration). Parsed output is not duplicated as raw text. Use `--include-raw` for original stdout and stderr; it implies `--json`. `--json-schema FILE` only requests a schema-shaped agy response; it does not select wrapper JSON output.

Capture the wrapper exit code directly. A pipeline's final command may mask it; use `pipefail` or save the code before processing output.

| Exit | Outcome | Meaning |
| --- | --- | --- |
| 0 | `ok` | Nonempty `SUCCESS`, no detected transport failure; inspect task completion separately |
| 10 | `timeout` | Print-timeout diagnostic or explicit timeout status; output may be partial |
| 11 | `incomplete` | Structured denied actions, known no-output diagnostic, or blank response |
| 12 | `agy_error` | CLI/dependency/runtime failure, malformed transport JSON, non-success status, or failed resume |
| 64 | `usage_error` | Invalid wrapper arguments or input |

`ok` can include a refusal, an explanation instead of an edit, or an invalid schema response. The wrapper does not classify prose. Read the answer and verify the requested artifacts/checks; do not interpret exit zero as task completion. Timeout evidence overrides agy's own exit zero and `SUCCESS`.

For example, inspect an answer from `none` mode even when the wrapper exits zero:

```bash
rc=0
/path/to/skill/scripts/agy-run.sh --json --write-level none \
  --prompt-file task.txt > result.json || rc=$?
jq -r '.result.response // ""' result.json
```

If `rc` is 0 but the answer says “I cannot run commands or edit files in this mode,” compare that limitation with the requested work and check whether the required edits/checks exist. If they are missing, report “Task incomplete: agy refused the required edits/commands in none mode; transport exit was 0.” Do not report completion or automatically raise the write level.

Reuse only a known `conversation_id` with `--resume ID`, reapplying the appropriate workspace, model, and write level. Do not guess IDs or use implicit latest-conversation continuation. After a timeout, establish whether the turn is still running before resuming or repeating work. The wrapper invokes agy once and never retries automatically. Any recovery should stay within the existing authorization and have a clear stopping condition.

A `warning: conversation "..." not found` diagnostic or a returned `conversation_id` differing from the requested `--resume` ID produces **12 / `agy_error`**, even if agy returns 0 and `SUCCESS`. This check precedes timeout classification. Text mode suppresses the response; JSON mode retains it only as diagnostic data in the error envelope. agy may already have started a new conversation; do not treat that answer as resumed work or automatically adopt its ID.

Preserve useful findings, paths, uncertainty, partial output, and verification gaps. Distinguish agy's reported checks from checks performed independently. A review alone authorizes reporting findings; existing authorization to implement fixes can cover a follow-up without asking again.

`--json-schema FILE` is best-effort: parse and validate the response separately before treating it as structured data. Prose, fenced JSON, or unexpected keys can still appear. Retain nonconforming output and report the validation failure.

Read [references/prompting.md](references/prompting.md) for task and follow-up examples, or [README.md](README.md) for the full wrapper interface and output contract.
