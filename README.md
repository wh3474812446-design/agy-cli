# agy-cli

适用于 Google Antigravity CLI（`agy`）的 Agent Skill 与高可靠非交互式封装工具。

`agy-cli` 提供了自动化接口（`scripts/agy-run.sh`），使 AI 助手和自动化工具能够执行单次非交互式 `agy` 轮次，用于限定范围的代码分析、代码审查以及经授权的实现任务。它结合了严格的输入校验、行为执行契约、机器可读的信封输出以及确定性的退出码。

---

## 概述 (Overview)

调用其他编程助手的自动化系统和 AI Agent 需要可预测的执行机制、清晰的错误边界以及可靠的输出格式。`agy-cli` 提供以下能力：

- **非交互式执行（Non-Interactive Execution）**：执行单次 `agy` 轮次，并将标准输入与终端输入断开（`</dev/null`），捕获 stdout、stderr 以及 CLI 状态码。
- **可配置的特权级别（Configurable Privilege Levels）**：实现三种写入级别（`none`、`files`、`commands`），注入定制的行为执行契约并配置 CLI 运行模式（`--mode plan`、`--mode accept-edits`、`--dangerously-skip-permissions`）。
- **可恢复的多轮会话（Resumable Multi-Turn Sessions）**：通过 `--resume ID` 跟踪 conversation ID 以支持多轮工作流，并校验会话完整性以防止静默的会话漂移。
- **结构化输出与确定性退出码（Structured Output & Deterministic Exit Codes）**：默认在 stdout 输出纯响应文本，并在 stderr 输出单行 JSON 元数据诊断信息；使用 `--json` 时在 stdout 输出紧凑的 Version 2 JSON 信封。通过独特的退出码明确区分超时、未完成的轮次、CLI 错误及无效用法。
- **Agent Skill 定义（Agent Skill Definition）**：随附 [`SKILL.md`](SKILL.md) 与 [`references/prompting.md`](references/prompting.md)，为自主 Agent 调用方提供提示词结构、事实锚定（grounding）指导和执行契约。

---

## 环境要求 (Requirements)

- **Bash**：4.4 或更高版本
- **`jq`**：用于 JSON 信封序列化以及 prompt / schema 校验
- **Antigravity CLI (`agy`)**：已安装并完成认证
  - 自动从 `PATH` 或 `~/.local/bin/agy` 发现
  - 可通过 `AGY_BIN` 环境变量指定自定义可执行文件路径（必须指向可执行文件路径，不能是 shell 命令或别名）

---

## 安装 (Installation)

将本仓库目录复制到 Agent 的 skills 目录即可安装 `agy-cli`：

1. **复制 skill 文件夹**：
   - 用户级技能（User-level skills）：
     ```bash
     cp -r /path/to/agy-cli ~/.gemini/antigravity-cli/skills/agy-cli
     ```
   - 仓库级技能（Repository-level skills）：
     ```bash
     cp -r /path/to/agy-cli /path/to/project/.agents/skills/agy-cli
     ```

2. **确保脚本具有可执行权限**：
   ```bash
   chmod +x scripts/agy-run.sh
   ```

---

## 快速开始 (Quick Start)

### 1. plan 模式下的分析任务（默认） (Analysis in plan mode (default))
在默认的 plan 模式（`--write-level none`）下针对项目工作区运行 prompt。请注意，plan 模式并非强制只读：

```bash
./scripts/agy-run.sh --cwd /path/to/project \
  'Explain the retry logic in src/client.ts and identify missing evidence.'
```

### 2. 通过 Heredoc 或管道传入多行输入 (Multi-line Input via Heredoc or Pipe)
使用带引号的 heredoc 或管道传递复杂 prompt。管道和常规文件会被自动识别：

```bash
./scripts/agy-run.sh --cwd /path/to/project <<'PROMPT'
Review src/orders/create.ts for race conditions and idempotency issues.
Report actionable findings with line numbers. Do not edit files or run shell commands.
PROMPT
```

### 3. 捕获 JSON 信封与退出码 (Capturing JSON Envelopes and Exit Codes)
使用 `--json` 在 stdout 上捕获结构化 JSON 输出并检查封装脚本的退出码：

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

> **管道注意事项（Pipeline Note）：** 在使用管道传递输出时（例如 `agy-run.sh ... | jq ...`），请确保启用了 `set -o pipefail` 或直接捕获退出状态，以避免掩盖封装脚本的错误。

---

## 选项参数 (Options)

`agy-run.sh` 接受以下选项：

| Option | Argument | Default | Description |
| --- | --- | --- | --- |
| `'PROMPT'` | String | 无（None） | 引号包裹的位置参数 prompt。仅提供一个带引号的 prompt。若 prompt 以 `-` 开头，请在其前使用 `--`。 |
| `--prompt-file` | `FILE` | 无（None） | 从 `FILE` 读取 prompt；`-` 表示标准输入（stdin）。不可与位置参数 prompt 同时使用。省略时，prompt 来自位置参数或隐式的管道 / 常规文件 stdin。 |
| `--cwd` | `DIR` | 当前目录（`$PWD`） | `agy` 执行的工作目录。 |
| `--model` | `ID` | 省略（Omitted） | 传递给 `agy` 的模型 ID（例如 `gemini-3.1-pro-low`）。 |
| `--effort` | `LEVEL` | 省略（Omitted） | 推理思考级别（Reasoning effort）：`low`、`medium`、`high`、`xhigh` 或 `max`。若指定了 `--model claude-*` 则会被拒绝。 |
| `--write-level` | `LEVEL` | `none` | 执行特权级别：`none`、`files` 或 `commands`。 |
| `--resume` | `ID` | 无（None） | 通过 ID 恢复已有会话（传递 `--conversation ID`）。 |
| `--timeout` | `DUR` | `600s` | `agy` 输出超时时间（print timeout）。接受形如 `120s`、`2m`、`1m30s`、`0.5s`、`500ms` 的 Go duration，或使用 `0` 禁用。 |
| `--add-dir` | `DIR` | 无（None） | 暴露给 `agy` 的额外工作区目录。可重复指定。 |
| `--json-schema` | `FILE` | 无（None） | 用于约束 `agy` 响应格式的 JSON schema 文件路径（尽力而为，best-effort）。 |
| `--json` | 无（None） | `false` | 在 stdout 输出紧凑的单行 JSON 信封。 |
| `--include-raw` | 无（None） | `false` | 在 JSON 信封中包含原始 raw stdout 和 stderr（隐含 `--json`）。 |
| `-h`, `--help` | 无（None） | 无（None） | 显示使用帮助并退出（退出码 `0`）。 |

### Prompt 输入规则与标准输入处理 (Prompt Input Rules & Stdin Handling)

1. **优先级（Precedence）**：位置参数 prompt 或 `--prompt-file FILE` 的优先级高于标准输入。不可同时使用位置参数 prompt 与 `--prompt-file`。
2. **隐式 Stdin 检测（Implicit Stdin Detection）**：当未提供 prompt 参数时，仅当 stdin 是管道（`-p /dev/stdin`）或常规文件（`-f /dev/stdin`，包含 heredoc）时才会读取 stdin。
3. **交互式与非 EOF 流保护（Interactive & Non-EOF Stream Protection）**：交互式终端（TTY）输入会立即被拒绝。打开的 socket 和字符设备（例如 `/dev/null`）会快速失败并返回退出码 `64`（`usage_error`），除非通过 `--prompt-file -` 显式请求。这可以防止自动化调用工具提供从不发送 EOF 的打开 socket 时发生挂起。
4. **EOF 要求（EOF Requirement）**：Stdin 流必须到达 EOF。脚本不会对读取 prompt 输入设置超时；`--timeout` 仅适用于 `agy` 执行阶段。
5. **Prompt 预算（Prompt Budget）**：Prompt 必须包含非空白文本且不包含 NUL（`\0`）字节。Prompt 文本本身以及最终 prompt（包含前置的 `<execution_contract>`）必须分别小于 120,000 字节。

---

## 写入级别与安全注意事项 (Write Levels and Safety Caveats)

所有写入级别都会自动以 `--sandbox` 运行 `agy`，并在 prompt 前置添加 `<execution_contract>` 代码块。

| Write Level | `agy` Execution Mode | Injected Execution Contract |
| --- | --- | --- |
| `none` *(default)* | `--mode plan` | `Do not modify files or run shell commands. Analyze using permitted read tools or the supplied context. Report limitations only when they affect the requested task.`<br>（禁止修改文件或运行 shell 命令。使用允许的读取工具或所提供的上下文进行分析。仅在限制影响请求任务时报告限制。） |
| `files` | `--mode accept-edits` | `Edit files only within the requested scope. Do not run shell commands. Report changed files and any verification gaps relevant to the task.`<br>（仅在请求范围内编辑文件。禁止运行 shell 命令。报告更改的文件以及与任务相关的任何验证缺口。） |
| `commands` | `--mode accept-edits --dangerously-skip-permissions` | `Edit files and run commands only within the requested scope. Permission auto-approval does not authorize unrelated or destructive actions. Report changed files and actual verification.`<br>（仅在请求范围内编辑文件和运行命令。权限自动批准不代表授权无关或破坏性操作。报告更改的文件和实际验证结果。） |

### 安全注意事项 (Safety Caveats)

- **Plan 模式并非操作系统边界（Plan Mode is Not an OS Boundary）**：在 `none` 模式下，`--mode plan` 和执行契约指示模型不要修改文件或执行命令。然而，plan 模式属于行为引导控制，**并非**操作系统强制实施的沙箱或只读文件系统边界。严格的只读隔离需要外部机制（例如容器化或只读挂载）来保障。
- **Commands 模式自动批准所有权限（Commands Mode Auto-Approves All Permissions）**：`commands` 级别会传递 `--dangerously-skip-permissions`，这将自动批准 `agy` 请求的**所有**工具权限，而不仅仅是 shell 执行。尽管 `agy` 内部的沙箱限制仍然有效，但权限自动批准的范围非常广泛。只有在任务明确授权了完整命令执行权限时，才应选择 `commands`。
- **禁止自动权限提权（No Automatic Privilege Escalation）**：出现权限拒绝（permission denied）错误时，绝不能通过自动切换到更高的写入级别来解决。权限设置必须严格反映经授权的任务边界。

---

## 输出格式 (Output Formats)

### 默认格式（文本模式） (Default (Text Mode))

- **标准输出（`stdout`）**：包含模型的响应文本（`.result.response`），并确保末尾包含换行符。当响应为空或会话恢复失败时，`stdout` 保持为空。
- **标准错误（`stderr`）**：包含恰好一行以 `agy-run: ` 为前缀的单行 JSON 元数据诊断信息：

```text
agy-run: {"outcome":"ok","exit_code":0,"agy_exit_code":0,"conversation_id":"example-conversation-id"}
```

当发生错误或出现非 `ok` 结果时，元数据对象中会出现额外的诊断字段：
- `message`：描述性的封装结果信息。
- `error`：当 `result.error` 存在且不同于响应文本时填充。
- `stderr`：CLI stderr 诊断信息（已针对 `result.error` 去重）。
- `raw_stdout`：当 JSON 反序列化失败时的未解析 CLI 输出。

元数据字段中内嵌的换行符均经过 JSON 转义，确保元数据输出始终保持在单行上。

### JSON 模式（--json 或 --include-raw） (JSON Mode (--json or --include-raw))

指定 `--json` 时，所有输出均作为紧凑的单行 Version 2 JSON 信封写入 `stdout`，且 `stderr` 保持为空：

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

信封 Schema（Envelope schema）：
- `version`：固定为整数 `2`。
- `outcome`：字符串标识符（`ok`、`timeout`、`incomplete`、`agy_error` 或 `usage_error`）。
- `exit_code`：`agy-run.sh` 返回的整数退出码。
- `agy_exit_code`：`agy` 返回的整数退出码，若 `agy` 未执行则为 `null`。
- `message`：人类可读的结果摘要。
- `conversation_id`：当前活跃的 conversation ID 字符串，或 `null`。
- `result`：从 `agy` stdout 解析出的 JSON 对象；若输出无法解析为 JSON 对象则为 `null`。
- `raw_stdout`：若传递了 `--include-raw`，或者 `result` 为 `null` 且原始 stdout 非空时包含此字段。
- `stderr`：若传递了 `--include-raw`，或者 CLI stderr 非空时包含此字段。

---

## 退出码 (Exit Codes)

`agy-run.sh` 使用明确的退出码对运行结果进行分类：

| Exit Code | Outcome | Meaning & Conditions |
| --- | --- | --- |
| **`0`** | `ok` | `agy` 返回了非空的 `SUCCESS` 状态且退出码为 `0`。**注意：** 需单独验证任务完成情况；模型拒绝或未满足的请求仍可能在传输层返回成功。 |
| **`10`** | `timeout` | 发生 `agy` 输出超时（print timeout，通过 stderr 上的 `print timeout after` 或状态 `TIMEOUT` / `TIMED_OUT` 检测）。输出可能不完整，且后台进程可能仍在运行。 |
| **`11`** | `incomplete` | 轮次结束但未完成请求的工作：记录了结构化的 `denied_actions`、输出了 `jetski: no output produced` 诊断信息，或者在没有超时诊断的情况下响应为空或仅包含空白字符。 |
| **`12`** | `agy_error` | 运行时或 CLI 故障：非零的 `agy` 退出码、缺少依赖（`jq`、`agy`）、二进制文件不可执行、结果 JSON 格式畸变、非成功状态或会话恢复失败。 |
| **`64`** | `usage_error` | 封装脚本调用无效：缺少选项参数、未知选项、Claude 模型搭配 `--effort`、超时格式无效、prompt / schema 文件不可读或超出大小限制、空白 / 包含 NUL 的 prompt，或在 TTY / 不受支持的流上缺失 prompt。 |

---

## 恢复会话 (Resuming Conversations)

若要跨多个轮次继续会话，请传入已知 `conversation_id` 的 `--resume <ID>`：

```bash
./scripts/agy-run.sh --cwd /path/to/project --resume "example-conversation-id" \
  --write-level files --prompt-file follow-up-fix.txt
```

### 会话完整性规则 (Session Integrity Rules)

- **重新指定上下文（Re-apply Context）**：为每个恢复的轮次显式指定合适的 `--cwd`、`--model` 以及授权的 `--write-level`。
- **不匹配与缺失会话检测（Mismatch & Missing Session Detection）**：如果 `agy` 在 stderr 上报告 `warning: conversation "..." not found`，或者返回的 `conversation_id` 与请求的 `--resume ID` 不同：
  - `agy-run.sh` 立即终止并返回退出码 **`12`（`agy_error`）**。
  - 在文本模式下，`stdout` 将被抑制（保持为空），以防止调用工具误将新启动会话的输出当作为已恢复的工作。
  - 在 JSON 模式下，信封会保留诊断详情。
  - 此项检查的优先级高于超时分类判定。
- **无自动重试（No Automatic Retries）**：封装脚本仅执行一次 `agy`，不会进行自动重试。发生超时后，在恢复会话之前请核实后台操作是否已完成，以避免产生重复的副作用。

---

## 已知限制 (Known Limitations)

- **超时行为（`--timeout`，Timeout Behavior）**：
  `--timeout DUR`（默认：`600s`，`0` 表示禁用）设置 `agy` 的 `--print-timeout`。这是 CLI 的输出截止时间（print deadline），**并非**操作系统的进程看门狗（watchdog）。在输出超时时，`agy` 本身会以状态 `SUCCESS` 退出且退出码为 0；返回退出码 10 的是 `agy-run.sh`。在 `agy` 打印部分输出后，后台工作可能仍在继续进行。
- **Plan 模式非强制隔离（Plan Mode Not Enforced）**：
  `--write-level none` 传递 `--mode plan` 并注入 prompt 指令。这是一种 Agent 行为约束，并非操作系统强制执行的文件系统沙箱或只读容器边界。
- **~128KB 操作系统参数限制（`ARG_MAX` / `MAX_ARG_STRLEN`）**：
  Linux 内核对单个参数大小限制约为 128 KiB（`MAX_ARG_STRLEN`，通常为 32 个内存页）。直接在命令行上提供过大的位置参数 prompt 会导致 Bash 在 `agy-run.sh` 执行前就报错并失败，提示 `Argument list too long`（退出码 `126`）。对于大型 prompt，请使用 `--prompt-file FILE` 或标准输入。封装脚本对 prompt 文本强制执行 120,000 字节的预算上限。
- **`--json-schema` 为尽力而为（`--json-schema` is Best Effort）**：
  `--json-schema FILE` 将 schema 转发给 `agy`（`--json-schema "$schema"`），但模型的遵循程度是尽力而为的。Schema 仅用于约束 `.result.response` 内部的 `agy` 输出，而非封装脚本自身的 JSON 信封。响应中仍可能包含散文文本、带围栏的 markdown 或非预期的键；调用方必须独立校验 `.result.response`。
- **Claude 模型拒绝 `--effort`（Claude Models Reject `--effort`）**：
  Claude 模型不支持 reasoning effort 选项。在指定 `--model claude-*` 的同时提供 `--effort` 会被封装脚本的选项校验捕获，并退出且返回退出码 **`64`（`usage_error`）**。
- **无效的 Resume ID 导致退出码 12（Invalid Resume ID Causes Exit 12）**：
  对于未知的会话 ID，`agy` 会静默启动一个新会话（退出码 0，stderr 警告）；封装脚本会检测到这一点，返回退出码 **`12`（`agy_error`）** 并抑制文本输出，此新会话不应被视为已恢复的会话。

---

## 运行测试 (Running Tests)

测试套件使用 `AGY_BIN` 针对本地 mock 可执行文件运行，对参数解析、stdin 检测、写入级别标志、超时处理以及 JSON 序列化进行验证：

```bash
python3 -m unittest tests/test_agy_run.py
```

或通过 unittest 测试发现机制运行：

```bash
python3 -m unittest discover -s tests -v
```

> **注意（Note）：** 测试不需要网络访问、API 凭据或已安装的 `agy` 二进制文件；所有调用均针对本地 Python stub 运行。

---

## 许可证 (License)

本项目基于 MIT 许可证开源。
