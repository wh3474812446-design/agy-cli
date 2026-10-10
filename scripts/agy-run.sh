#!/usr/bin/env bash
# One non-interactive agy turn; text by default, a JSON envelope with --json.
set -u
set -o pipefail
umask 077
export LC_ALL=C
# A caller's CDPATH must not redirect relative workspace paths or add cd output.
unset CDPATH

help() {
  cat <<'HELP'
Usage: agy-run.sh [OPTIONS] < prompt.txt
       agy-run.sh [OPTIONS] --prompt-file FILE
       agy-run.sh [OPTIONS] [--] 'PROMPT'

  --cwd DIR                  Working directory (default: current directory)
  --model ID                 Model ID; omitted by default
  --effort LEVEL             low|medium|high|xhigh|max; omitted by default
  --write-level LEVEL        none|files|commands (default: none)
  --resume ID                Resume a specific conversation
  --timeout DUR              agy print timeout (default: 600s; 0 disables)
  --prompt-file FILE         Read prompt from FILE; '-' means stdin
  --add-dir DIR              Add workspace directory (repeatable)
  --json-schema FILE         Pass a JSON schema file; response is best-effort
  --json                     Emit a compact JSON envelope to stdout
  --include-raw              Include original stdout/stderr; implies --json
  -h, --help                 Show this help

Requires Bash 4.4+, jq, and agy on PATH or at ~/.local/bin/agy.
AGY_BIN may select an executable path (not a shell command).
All write levels use --sandbox. 'none' uses plan mode, which is NOT an
OS-enforced read-only boundary. 'commands' also auto-approves permissions.
Exit: 0 ok; 10 timeout; 11 denied/incomplete; 12 agy/runtime error; 64 usage.
Default output: response on stdout, one metadata/diagnostic line on stderr.
Supply one quoted prompt OR --prompt-file; otherwise read stdin only from
a pipe or regular file (including heredocs). Missing input exits 64.
Sockets/devices require --prompt-file -; TTY input is rejected.
Stdin reads require EOF; --timeout applies only to agy, not input reading.
Explicit prompt input takes precedence over stdin. Use -- before a prompt
starting with '-'. --json-schema shapes agy's response, not wrapper output.
HELP
}

# Help remains available even before dependencies are installed.
if [[ $# == 1 && ( $1 == --help || $1 == -h ) ]]; then help; exit 0; fi
if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' 'agy-run: jq is required.' >&2
  exit 12
fi

scratch=$(mktemp -d "${TMPDIR:-/tmp}/agy-run.XXXXXXXX") || {
  printf '%s\n' 'agy-run: cannot create private temporary directory.' >&2
  exit 12
}
trap 'rm -rf -- "$scratch"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for name in stdout stderr prompt result; do
  if ! : > "$scratch/$name"; then
    printf '%s\n' 'agy-run: cannot initialize temporary files.' >&2
    exit 12
  fi
done
printf 'null\n' > "$scratch/result"
agy_rc=null
json_output=false
include_raw=false

finish() {
  local code=$1 outcome=$2 message=$3 suppress_response=${4:-false}
  # --rawfile avoids a second argv-size limit for potentially large results.
  jq -cn --arg outcome "$outcome" --arg message "$message" \
    --argjson code "$code" --argjson agy_rc "$agy_rc" \
    --argjson include_raw "$include_raw" \
    --slurpfile parsed "$scratch/result" \
    --rawfile raw "$scratch/stdout" --rawfile err "$scratch/stderr" '
    ($parsed[0] // null) as $result |
    {version:2, outcome:$outcome, exit_code:$code, agy_exit_code:$agy_rc,
     message:$message,
     conversation_id:(if ($result | type) == "object" and
       ($result.conversation_id | type) == "string" and
       ($result.conversation_id | length) > 0
       then $result.conversation_id else null end),
     result:$result}
    + (if $include_raw or ($result == null and $raw != "")
       then {raw_stdout:$raw} else {} end)
    + (if $include_raw or $err != "" then {stderr:$err} else {} end)' \
    > "$scratch/envelope" || {
    printf '%s\n' 'agy-run: failed to serialize result envelope.' >&2
    exit 12
  }
  if [[ $json_output == true ]]; then
    cat -- "$scratch/envelope" || exit 12
  else
    # Keep the answer separate from status so stdout can be saved as text/JSON.
    jq -jr --argjson suppress_response "$suppress_response" '
      if ($suppress_response | not) and
        (.result.response | type) == "string" and .result.response != ""
      then .result.response | if endswith("\n") then . else . + "\n" end
      else empty end' "$scratch/envelope" || exit 12
    jq -cr '
      def trim: if type == "string" then gsub("^\\s+|\\s+$"; "") else "" end;
      . as $env |
      {outcome, exit_code, agy_exit_code, conversation_id}
      + (if .outcome != "ok" then {message} else {} end)
      + (if .result.error != null and .result.error != ""
         and .result.error != .result.response
         then {error:.result.error} else {} end)
      + (if (.stderr // "" | trim) != "" and
         (.stderr | trim | sub("^error: *"; "")) != ($env.result.error // "" | trim)
         then {stderr:.stderr} else {} end)
      + (if has("raw_stdout") and .result == null then {raw_stdout} else {} end)
      | "agy-run: " + tojson' "$scratch/envelope" >&2 || exit 12
  fi
  exit "$code"
}
usage_error() { finish 64 usage_error "$1"; }
need_value() {
  [[ $# -ge 2 && -n $2 && $2 != --* ]] || usage_error "Missing value for $1"
}

cwd=$PWD
model=''
effort=''
write_level=none
resume=''
timeout=600s
prompt_file=-
prompt_given=false
positional_given=false
positional_prompt=''
schema_file=''
add_dirs=()
while (( $# )); do
  case $1 in
    --cwd) need_value "$@"; cwd=$2; shift 2 ;;
    --model) need_value "$@"; model=$2; shift 2 ;;
    --effort) need_value "$@"; effort=$2; shift 2 ;;
    --write-level) need_value "$@"; write_level=$2; shift 2 ;;
    --resume) need_value "$@"; resume=$2; shift 2 ;;
    --timeout) need_value "$@"; timeout=$2; shift 2 ;;
    --prompt-file)
      need_value "$@"
      [[ $prompt_given == false ]] || usage_error 'Specify --prompt-file only once'
      prompt_given=true; prompt_file=$2; shift 2 ;;
    --add-dir) need_value "$@"; add_dirs+=("$2"); shift 2 ;;
    --json-schema) need_value "$@"; schema_file=$2; shift 2 ;;
    --json) json_output=true; shift ;;
    --include-raw) json_output=true; include_raw=true; shift ;;
    -h|--help) help; exit 0 ;;
    --)
      shift
      (( $# == 1 )) || usage_error 'Expected one quoted prompt after --'
      [[ $positional_given == false ]] || usage_error 'Supply only one quoted prompt'
      positional_given=true; positional_prompt=$1; shift ;;
    -*) usage_error "Unknown option: $1" ;;
    *)
      [[ $positional_given == false ]] || usage_error 'Supply only one quoted prompt'
      positional_given=true; positional_prompt=$1; shift ;;
  esac
done
[[ $prompt_given == false || $positional_given == false ]] || \
  usage_error 'Choose a positional prompt or --prompt-file, not both'
case $write_level in none|files|commands) ;; *) usage_error 'Invalid --write-level' ;; esac
case $effort in ''|low|medium|high|xhigh|max) ;; *) usage_error 'Invalid --effort' ;; esac
if [[ ${model,,} == claude-* && -n $effort ]]; then
  usage_error 'Claude models reject --effort; omit it'
fi
# Accept a practical subset of Go durations, including 1m30s and 0.5s.
if [[ $timeout != 0 && ! $timeout =~ ^([0-9]+([.][0-9]+)?(ms|s|m|h))+$ ]]; then
  usage_error 'Invalid --timeout: use 120s, 2m, 1m30s, 0.5s, or 0'
fi
[[ -d $cwd ]] || usage_error "Working directory does not exist: $cwd"

# Resolve all caller-supplied paths before changing cwd.
cwd=$(cd -- "$cwd" && pwd -P) || usage_error 'Cannot access working directory'
for i in "${!add_dirs[@]}"; do
  [[ -d ${add_dirs[i]} ]] || usage_error "Additional directory does not exist: ${add_dirs[i]}"
  add_dirs[i]=$(cd -- "${add_dirs[i]}" && pwd -P) || usage_error 'Cannot access additional directory'
done
schema=''
if [[ -n $schema_file ]]; then
  [[ -f $schema_file && -r $schema_file ]] || usage_error 'Schema must be a readable regular file'
  schema=$(jq -ces 'if length == 1 and (.[0] | type) == "object" then .[0] else error("Expected one schema object") end' -- "$schema_file" 2> "$scratch/stderr") \
    || usage_error 'Schema must contain one JSON object'
  (( ${#schema} < 120000 )) || usage_error 'Schema is too large for one CLI argument'
fi

if [[ $positional_given == true ]]; then
  printf '%s' "$positional_prompt" > "$scratch/prompt" || usage_error 'Could not store prompt'
elif [[ $prompt_file == - ]]; then
  [[ ! -t 0 ]] || usage_error 'Supply a quoted prompt, --prompt-file, or redirected stdin'
  # Agent tools may supply an open socket that never sends EOF. Only infer
  # prompt input from a pipe/file; other non-TTY streams require explicit opt-in.
  [[ $prompt_given == true || -p /dev/stdin || -f /dev/stdin ]] || \
    usage_error 'Supply a quoted prompt, --prompt-file FILE, or pipe/redirect a prompt; use --prompt-file - to explicitly read stdin'
  cat > "$scratch/prompt" || usage_error 'Could not read prompt from stdin'
else
  [[ -f $prompt_file && -r $prompt_file ]] || usage_error 'Prompt must be a readable regular file'
  cat -- "$prompt_file" > "$scratch/prompt" || usage_error 'Could not read prompt file'
fi
# Bash argv cannot represent NUL. Check before loading the prompt into a variable.
if ! jq -eRs 'length > 0 and (test("\\S")) and (index("\u0000") == null)' "$scratch/prompt" >/dev/null; then
  usage_error 'Prompt must be nonblank text without NUL bytes'
fi
size=$(wc -c < "$scratch/prompt") || finish 12 agy_error 'Could not measure prompt'
(( size < 120000 )) || usage_error 'Prompt is too large; keep it below 120000 bytes and reference files for context'
# A sentinel preserves trailing newlines removed by ordinary command substitution.
prompt=$(cat -- "$scratch/prompt"; printf '.')
prompt=${prompt%.}
case $write_level in
  none) contract='Do not modify files or run shell commands. Analyze using permitted read tools or the supplied context. Report limitations only when they affect the requested task.' ;;
  files) contract='Edit files only within the requested scope. Do not run shell commands. Report changed files and any verification gaps relevant to the task.' ;;
  commands) contract='Edit files and run commands only within the requested scope. Permission auto-approval does not authorize unrelated or destructive actions. Report changed files and actual verification.' ;;
esac
prompt="<execution_contract>
$contract
</execution_contract>
$prompt"
(( ${#prompt} < 120000 )) || usage_error 'Prompt plus execution contract exceeds the 120000-byte argument budget'

if [[ -n ${AGY_BIN:-} ]]; then
  binary=$(command -v -- "$AGY_BIN") || finish 12 agy_error 'AGY_BIN executable was not found'
elif command -v agy >/dev/null 2>&1; then
  binary=$(command -v agy)
elif [[ -x ${HOME:-}/.local/bin/agy ]]; then
  binary=$HOME/.local/bin/agy
else
  finish 12 agy_error 'agy was not found on PATH or at ~/.local/bin/agy'
fi
[[ $binary == /* ]] || binary=$PWD/$binary
[[ -f $binary && -x $binary ]] || finish 12 agy_error 'agy must resolve to an executable file'

args=(--output-format json --print-timeout "$timeout" --sandbox)
if [[ $write_level == none ]]; then
  args+=(--mode plan)
else
  args+=(--mode accept-edits)
fi
[[ $write_level != commands ]] || args+=(--dangerously-skip-permissions)
[[ -z $model ]] || args+=(--model "$model")
[[ -z $effort ]] || args+=(--effort "$effort")
[[ -z $resume ]] || args+=(--conversation "$resume")
[[ -z $schema ]] || args+=(--json-schema "$schema")
for dir in "${add_dirs[@]}"; do args+=(--add-dir "$dir"); done
args+=(-p "$prompt")

# Never allow agy to consume prompt input or request terminal input.
(cd -- "$cwd" && exec "$binary" "${args[@]}" </dev/null) > "$scratch/stdout" 2> "$scratch/stderr"
agy_rc=$?
# Accept exactly one JSON object, retaining malformed output in raw_stdout.
if ! jq -es 'if length == 1 and (.[0] | type) == "object" then .[0] else error("Expected one result object") end' \
    "$scratch/stdout" > "$scratch/result" 2>/dev/null; then
  printf 'null\n' > "$scratch/result"
fi

# A failed resume can silently start a new conversation with SUCCESS/exit 0.
# Reject it before other outcomes; its answer is not from the requested context.
if grep -Eiq 'warning:[[:space:]]+conversation[[:space:]]+.+[[:space:]]+not found' "$scratch/stderr"; then
  finish 12 agy_error 'agy reported conversation not found; it may have started a new conversation; do not use this response as resumed work' true
fi
if [[ -n $resume ]] && jq -e --arg resume "$resume" '
    (.conversation_id | type) == "string" and .conversation_id != $resume' \
    "$scratch/result" >/dev/null; then
  finish 12 agy_error 'agy returned a conversation_id different from the requested --resume ID; do not use this response as resumed work' true
fi

# Otherwise timeout evidence takes precedence, even over SUCCESS/exit 0 or bad JSON.
if grep -Eiq 'print timeout after' "$scratch/stderr" ||
    jq -e '.status == "TIMEOUT" or .status == "TIMED_OUT"' "$scratch/result" >/dev/null; then
  finish 10 timeout 'agy timed out; output may be partial and the conversation may still be running'
fi
if (( agy_rc != 0 )); then
  finish 12 agy_error 'agy exited unsuccessfully; inspect stderr and agy_exit_code'
fi
if grep -Eiq 'jetski: no output produced' "$scratch/stderr"; then
  finish 11 incomplete 'agy produced a no-output diagnostic; the turn is incomplete'
fi
if ! jq -e 'type == "object" and (.status | type) == "string" and
    (.response | type) == "string" and (.conversation_id | type) == "string" and
    (if has("denied_actions") then
      (.denied_actions | type) == "array"
     else true end)' "$scratch/result" >/dev/null; then
  finish 12 agy_error 'agy returned malformed or unexpected result JSON'
fi
if ! jq -e '.status == "SUCCESS"' "$scratch/result" >/dev/null; then
  finish 12 agy_error 'agy reported a non-success status; inspect result'
fi
if jq -e '(.denied_actions // [] | length) > 0' "$scratch/result" >/dev/null; then
  finish 11 incomplete 'Actions were denied or no output was produced; do not treat this as completed work'
fi
if ! jq -e '.response | test("\\S")' "$scratch/result" >/dev/null; then
  finish 11 incomplete 'agy returned an empty response without a known timeout diagnostic'
fi
finish 0 ok 'agy returned a nonempty successful response; verify task-level completeness separately'
