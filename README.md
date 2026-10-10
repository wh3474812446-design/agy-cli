# agy-cli

An agent skill and robust non-interactive wrapper for Google's Antigravity CLI (`agy`).

`agy-cli` provides an automated interface (`scripts/agy-run.sh`) that enables AI assistants and automation tools to execute single, non-interactive `agy` turns for scoped analysis, code reviews, and authorized implementation tasks. It combines strict input validation, behavioral execution contracts, machine-readable envelope output, and deterministic exit codes.

---

## Overview

Automated systems and AI agents calling other coding assistants need predictable execution, clear error boundaries, and reliable output formats. `agy-cli` provides:

- **Non-Interactive Execution**: Executes a single `agy` turn with standard input disconnected from terminal input (`</dev/null`), capturing stdout, stderr, and the CLI status code.
- **Configurable Privilege Levels**: Implements three write levels (`none`, `files`, `commands`) that inject tailored behavioral contracts and configure CLI operational modes (`--mode plan`, `--mode accept-edits`, `--dangerously-skip-permissions`).
- **Resumable Multi-Turn Sessions**: Tracks conversation IDs with `--resume ID` to support multi-turn workflows, verifying session integrity to prevent silent session drift.
- **Structured Output & Deterministic Exit Codes**: Emits plain response text with a single-line JSON metadata line on stderr by default, or a compact Version 2 JSON envelope on stdout with `--json`. Distinguishes timeouts, incomplete turns, CLI errors, and invalid usage with unique exit codes.
- **Agent Skill Definition**: Ships with [`SKILL.md`](SKILL.md) and [`references/prompting.md`](references/prompting.md), providing prompt structures, grounding guidelines, and execution contracts for autonomous agent callers.

---

## Requirements

- **Bash**: Version 4.4 or higher
- **`jq`**: Required for JSON envelope serialization and prompt/schema validation
- **Antigravity CLI (`agy`)**: Installed and authenticated
  - Discovered automatically on `PATH` or at `~/.local/bin/agy`
  - Custom executable path can be set using the `AGY_BIN` environment variable (must point to an executable file path, not a shell command or alias)

---

## Installation

Install `agy-cli` by copying the repository directory into your agent's skills directory:

1. **Copy the skill folder**:
   - For user-level skills:
     ```bash
     cp -r /path/to/agy-cli ~/.gemini/antigravity-cli/skills/agy-cli
     ```
   - For repository-level skills:
     ```bash
     cp -r /path/to/agy-cli /path/to/project/.agents/skills/agy-cli
     ```

2. **Ensure the script is executable**:
   ```bash
   chmod +x scripts/agy-run.sh
   ```

---

## Quick Start

### 1. Analysis in plan mode (default)
Run a prompt against a project workspace in default plan mode (`--write-level none`). Note that plan mode is not enforced read-only:

```bash
./scripts/agy-run.sh --cwd /path/to/project \
  'Explain the retry logic in src/client.ts and identify missing evidence.'
```

### 2. Multi-line Input via Heredoc or Pipe
Pass complex prompts using a quoted heredoc or pipe. Pipes and regular files are automatically recognized:

```bash
./scripts/agy-run.sh --cwd /path/to/project <<'PROMPT'
Review src/orders/create.ts for race conditions and idempotency issues.
Report actionable findings with line numbers. Do not edit files or run shell commands.
PROMPT
```

### 3. Capturing JSON Envelopes and Exit Codes
Use `--json` to capture structured JSON output on stdout and inspect wrapper exit codes:

```bash
rc=0
./scripts/agy-run.sh --json --cwd /path/to/project \
  --prompt-file task.txt > result.json || rc=$?

if [ "$rc" -eq 0 ]; then
  echo "Response:"
  jq -r '.result.response' result.json
else
  echo "Error (exit code $rc):"
  jq '{outcome, message, conversation_id, stderr}' result.json
fi
```

> **Pipeline Note:** When piping output (e.g., `agy-run.sh ... | jq ...`), ensure `set -o pipefail` is active or capture the exit status directly to avoid masking wrapper errors.

---

## Options

`agy-run.sh` accepts the following options:

| Option | Argument | Default | Description |
| --- | --- | --- | --- |
| `'PROMPT'` | String | None | Quoted positional prompt. Supply one quoted prompt. Use `--` before prompts starting with `-`. |
| `--prompt-file` | `FILE` | None | Read prompt from `FILE`; `-` means stdin. Cannot be combined with a positional prompt. When omitted, the prompt comes from the positional argument or implicit pipe/regular-file stdin. |
| `--cwd` | `DIR` | Current directory (`$PWD`) | Working directory for `agy` execution. |
| `--model` | `ID` | Omitted | Model ID passed to `agy` (e.g., `gemini-3.1-pro-low`). |
| `--effort` | `LEVEL` | Omitted | Reasoning effort: `low`, `medium`, `high`, `xhigh`, or `max`. Rejected if `--model claude-*`. |
| `--write-level` | `LEVEL` | `none` | Execution privilege level: `none`, `files`, or `commands`. |
| `--resume` | `ID` | None | Resume an existing conversation by ID (passes `--conversation ID`). |
| `--timeout` | `DUR` | `600s` | `agy` print timeout. Accepts Go durations like `120s`, `2m`, `1m30s`, `0.5s`, `500ms`, or `0` to disable. |
| `--add-dir` | `DIR` | None | Additional workspace directory exposed to `agy`. Repeatable. |
| `--json-schema` | `FILE` | None | Path to a JSON schema file shaping `agy`'s response (best-effort). |
| `--json` | None | `false` | Emit a compact single-line JSON envelope to stdout. |
| `--include-raw` | None | `false` | Include original raw stdout and stderr in the JSON envelope (implies `--json`). |
| `-h`, `--help` | None | None | Display usage help and exit `0`. |

### Prompt Input Rules & Stdin Handling

1. **Precedence**: A positional prompt or `--prompt-file FILE` takes precedence over standard input. You cannot combine a positional prompt with `--prompt-file`.
2. **Implicit Stdin Detection**: When no prompt argument is provided, stdin is read only if it is a pipe (`-p /dev/stdin`) or a regular file (`-f /dev/stdin`, including heredocs).
3. **Interactive & Non-EOF Stream Protection**: Interactive terminal (TTY) input is rejected immediately. Open sockets and character devices (e.g., `/dev/null`) fail fast with exit code `64` (`usage_error`) unless explicitly requested with `--prompt-file -`. This prevents hangs when automated caller tools provide an open socket that never sends EOF.
4. **EOF Requirement**: Stdin streams must reach EOF. The script does not apply a timeout to reading prompt input; `--timeout` applies only to the `agy` execution phase.
5. **Prompt Budget**: Prompts must contain non-blank text without NUL (`\0`) bytes. The prompt text and the final prompt (including the prepended `<execution_contract>`) must each be under 120,000 bytes.

---

## Write Levels and Safety Caveats

Every write level automatically runs `agy` with `--sandbox` and prepends an `<execution_contract>` block to the prompt.

| Write Level | `agy` Execution Mode | Injected Execution Contract |
| --- | --- | --- |
| `none` *(default)* | `--mode plan` | `Do not modify files or run shell commands. Analyze using permitted read tools or the supplied context. Report limitations only when they affect the requested task.` |
| `files` | `--mode accept-edits` | `Edit files only within the requested scope. Do not run shell commands. Report changed files and any verification gaps relevant to the task.` |
| `commands` | `--mode accept-edits --dangerously-skip-permissions` | `Edit files and run commands only within the requested scope. Permission auto-approval does not authorize unrelated or destructive actions. Report changed files and actual verification.` |

### Safety Caveats

- **Plan Mode is Not an OS Boundary**: In `none` mode, `--mode plan` and the contract instruct the model not to modify files or execute commands. However, plan mode is a behavioral guidance control, **not** an operating-system-enforced sandbox or read-only filesystem boundary. Strict read-only isolation requires external enforcement (such as containerization or read-only mounts).
- **Commands Mode Auto-Approves All Permissions**: The `commands` level passes `--dangerously-skip-permissions`, which automatically approves **all** tool permissions requested by `agy`, not only shell execution. While `agy`'s internal sandbox restrictions remain active, permission auto-approval is broad. Only select `commands` when full command execution has been explicitly authorized for the task.
- **No Automatic Privilege Escalation**: Permission denied errors must not be resolved by automatically switching to a higher write level. Permission settings must strictly reflect authorized task boundaries.

---

## Output Formats

### Default (Text Mode)

- **Standard Output (`stdout`)**: Contains the model's response text (`.result.response`), ensuring a trailing newline. On empty responses or failed resumes, `stdout` remains empty.
- **Standard Error (`stderr`)**: Contains exactly one single-line JSON metadata diagnostic prefixed by `agy-run: `:

```text
agy-run: {"outcome":"ok","exit_code":0,"agy_exit_code":0,"conversation_id":"example-conversation-id"}
```

When an error or non-`ok` outcome occurs, additional diagnostic fields are present in the metadata object:
- `message`: Descriptive wrapper outcome message.
- `error`: Populated if `result.error` exists and is distinct from the response text.
- `stderr`: CLI stderr diagnostic (deduplicated against `result.error`).
- `raw_stdout`: Unparsed CLI output if JSON deserialization failed.

Embedded newlines within metadata fields are JSON-escaped, guaranteeing that the metadata output stays on a single line.

### JSON Mode (`--json` or `--include-raw`)

When `--json` is specified, all output is written to `stdout` as a compact, single-line Version 2 JSON envelope, and `stderr` remains empty:

```json
{
  "version": 2,
  "outcome": "ok",
  "exit_code": 0,
  "agy_exit_code": 0,
  "message": "agy returned a nonempty successful response; verify task-level completeness separately",
  "conversation_id": "example-conversation-id",
  "result": {
    "conversation_id": "example-conversation-id",
    "status": "SUCCESS",
    "response": "Analysis findings...",
    "duration_seconds": 12.4,
    "usage": { "total_tokens": 120 }
  }
}
```

Envelope schema:
- `version`: Always integer `2`.
- `outcome`: String identifier (`ok`, `timeout`, `incomplete`, `agy_error`, or `usage_error`).
- `exit_code`: Integer exit code returned by `agy-run.sh`.
- `agy_exit_code`: Integer exit code returned by `agy`, or `null` if `agy` was not executed.
- `message`: Human-readable summary of the outcome.
- `conversation_id`: Active conversation ID string, or `null`.
- `result`: Parsed JSON object from `agy` stdout, or `null` if output could not be parsed as a JSON object.
- `raw_stdout`: Included if `--include-raw` is passed, or if `result` is `null` and raw stdout was non-empty.
- `stderr`: Included if `--include-raw` is passed, or if CLI stderr was non-empty.

---

## Exit Codes

`agy-run.sh` categorizes outcomes using explicit exit codes:

| Exit Code | Outcome | Meaning & Conditions |
| --- | --- | --- |
| **`0`** | `ok` | `agy` returned a non-empty `SUCCESS` status with exit code `0`. **Note:** Verify task completion separately; model refusals or unfulfilled requests can still yield transport success. |
| **`10`** | `timeout` | `agy` print timeout occurred (detected via `print timeout after` on stderr or status `TIMEOUT` / `TIMED_OUT`). Output may be partial, and backend processes may still be running. |
| **`11`** | `incomplete` | Turn ended without completing requested work: structured `denied_actions` were recorded, a `jetski: no output produced` diagnostic was emitted, or the response was empty/whitespace-only without a timeout diagnostic. |
| **`12`** | `agy_error` | Runtime or CLI failure: non-zero `agy` exit code, missing dependencies (`jq`, `agy`), unexecutable binary, malformed result JSON, non-success status, or a failed conversation resume. |
| **`64`** | `usage_error` | Invalid wrapper invocation: missing option arguments, unknown options, Claude with `--effort`, invalid timeout format, unreadable or oversized prompt/schema files, blank/NUL prompt, or missing prompt on TTY/unsupported streams. |

---

## Resuming Conversations

To continue a conversation across multiple turns, pass `--resume <ID>` with a known `conversation_id`:

```bash
./scripts/agy-run.sh --cwd /path/to/project --resume "example-conversation-id" \
  --write-level files --prompt-file follow-up-fix.txt
```

### Session Integrity Rules

- **Re-apply Context**: Specify the appropriate `--cwd`, `--model`, and authorized `--write-level` for each resumed turn.
- **Mismatch & Missing Session Detection**: If `agy` reports `warning: conversation "..." not found` on stderr, or if the returned `conversation_id` differs from the requested `--resume ID`:
  - `agy-run.sh` immediately terminates with exit code **`12` (`agy_error`)**.
  - In text mode, `stdout` is suppressed to prevent caller tools from mistaking output from a newly initiated session for resumed work.
  - In JSON mode, the envelope retains the diagnostic details.
  - This check takes precedence over timeout classification.
- **No Automatic Retries**: The wrapper executes `agy` once without automatic retries. Following a timeout, verify whether backend actions completed before resuming to avoid duplicate side effects.

---

## Known Limitations

- **Timeout Behavior (`--timeout`)**:
  `--timeout DUR` (default: `600s`, `0` to disable) sets `agy`'s `--print-timeout`. This is a CLI print deadline, **not** an OS process watchdog. On print timeout, `agy` itself exits 0 with status `SUCCESS`; it is `agy-run.sh` that returns exit 10. Backend work can continue after `agy` prints partial output.
- **Plan Mode Not Enforced**:
  `--write-level none` passes `--mode plan` and injects prompt instructions. This is an agent behavioral constraint, not an OS-enforced filesystem sandbox or read-only container boundary.
- **~128KB OS Argument Limit (`ARG_MAX` / `MAX_ARG_STRLEN`)**:
  Linux kernels enforce an individual argument size limit of approximately 128 KiB (`MAX_ARG_STRLEN`, typically 32 memory pages). Supplying large positional prompts directly on the command line causes Bash to fail with `Argument list too long` (exit code `126`) before `agy-run.sh` can execute. Use `--prompt-file FILE` or stdin for large prompts. The wrapper enforces a 120,000-byte budget on prompt text.
- **`--json-schema` is Best Effort**:
  `--json-schema FILE` forwards the schema to `agy` (`--json-schema "$schema"`), but adherence by the model is best-effort. The schema shapes `agy`'s output inside `.result.response`, not the wrapper's JSON envelope. The response may contain prose, fenced markdown, or unexpected keys; callers must validate `.result.response` independently.
- **Claude Models Reject `--effort`**:
  Claude models do not support the reasoning effort flag. Supplying `--effort` when `--model claude-*` is specified is caught by wrapper option validation and exits with code **`64` (`usage_error`)**.
- **Invalid Resume ID Causes Exit 12**:
  `agy` silently starts a new conversation for an unknown ID (exit 0, stderr warning); the wrapper detects that and returns exit code **`12` (`agy_error`)** and suppresses text output, and the new conversation should not be treated as resumed.

---

## Running Tests

The test suite exercises argument parsing, stdin detection, write level flags, timeout handling, and JSON serialization against a local mock executable using `AGY_BIN`:

```bash
python3 -m unittest tests/test_agy_run.py
```

Or via unittest test discovery:

```bash
python3 -m unittest discover -s tests -v
```

> **Note:** Tests do not require network access, API credentials, or an installed `agy` binary; all invocations run against a local Python stub.

---

## License

This project is licensed under the MIT License.
