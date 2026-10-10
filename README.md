# agy-cli：让你的 AI 助手把脏活累活一键甩给 Antigravity

如果你平时在用 **Claude Code**、**Cursor**、**Grok Bot** 或者自己搭的 AI Agent，你一定遇到过这些头疼的场景：
- 想让它做一次全仓库的深层代码审查，或者重构某个复杂模块，但怕它吃满当前对话的上下文（Context），甚至把你的工作界面搞卡死；
- 想让它帮忙写长代码、画图生图，或者跑耗时好几分钟的后台长任务，但主助手挂在终端里动弹不得；
- 想调用 Google Antigravity（`agy`），又担心它在命令行里冷不丁弹个交互提示卡住，或者执行出错了程序根本不知道怎么判断。

**`agy-cli` 就是为你和你的 AI 助手量身打造的“任务外包小工具”**（也可以直接作为 Agent Skill 接入）。通过一行清爽的脚本（`scripts/agy-run.sh`），你的助手就能安全、省心、全自动地发起一次 Antigravity 运行，把各种重活大活稳妥甩出去！随附的 [`SKILL.md`](SKILL.md) 与 [`references/prompting.md`](references/prompting.md) 还准备了开箱即用的技能定义和提示词范例。

---

## 为什么你的助手值得用它？

### 1. 脏活累活随便甩，能力互补不卡顿
不管是通读十几个文件的复杂分析、全项目找 Bug、生图画图，还是耗时较长的代码编写与重构，主助手只需要把需求打个包，用一行命令丢给 Antigravity 去跑。跑完直接拿结果，主助手的上下文干净清爽，主进程也绝不会被交互提示挂起。

### 2. 三档权限把关，控制权牢牢握在手里
把任务交给外部工具，最怕它自作主张删库改代码。`agy-cli` 贴心地设计了三档权限级别（`--write-level`），让你的助手随时决定放权多少：
- **`none`（默认只分析）**：只动嘴不动手，禁止修改任何文件、禁止运行任何 shell 命令；
- **`files`（允许改代码）**：允许在限定范围内改动文件，但严禁跑终端命令；
- **`commands`（完全放行）**：允许改文件，并且自动放行工具和命令执行。

每种模式都会自动在提示词前注入一段明确的英文行为公约（`<execution_contract>` 代码块，给 AI 上紧箍咒），并开启 Antigravity 沙箱，把动作规规矩矩管住。

### 3. 支持多轮对话，顺着上下文继续聊
任务不是一锤子买卖？完全没问题！只要带上上一次返回的会话 ID（`--resume <ID>`），就能顺着同一段对话继续追问、调整方案或者派发下一步任务。上下文不丢失，不用每次从头给它科普背景。

### 4. 退出码清清楚楚，自动化调用绝不抓瞎
搞脚本和 Agent 联动，最烦的就是“看起来跑完了，其实报错了”或者“报错了但不知道为啥”。`agy-cli` 的退出状态设计得极其规整、绝不含糊：
- **退出码一眼看懂**：是成功干完（`0`）、超时了（`10`）、动作被拒或活没干完（`11`）、CLI/环境故障（`12`），还是参数传错了（`64`），程序判断毫不费力；
- **输出干净利索**：默认模式下，最终回答走 stdout，诊断信息单行进 stderr，互不干扰；加个 `--json` 还能直接拿到包含 Token 消耗、耗时、完整状态的单行紧凑 JSON 结果包（Version 2 结构）。

---

## 环境准备 (Requirements)

开始使用前，请确保环境中已具备以下工具：

- **Bash**：4.4 或更高版本
- **`jq`**：必须安装（用于组装 JSON 结果包以及校验 prompt / schema）
- **Google Antigravity CLI (`agy`)**：系统中已安装并完成登录认证
  - 脚本会自动从系统 `PATH` 或 `~/.local/bin/agy` 寻找可执行文件；
  - 如果安装在自定义路径，可以通过 `AGY_BIN` 环境变量指定可执行文件路径（必须是指向二进制文件的路径，不能是 shell 别名或复合命令；本脚本不会自动安装或登录 `agy`）。

---

## 安装方法 (Installation)

你可以直接把它当作项目脚本调用，也可以把它装进你助手的 skills 技能目录中：

1. **复制 skill 文件夹**：
   - 助手用户级技能（User-level skills）：
     ```bash
     cp -r /path/to/agy-cli ~/.gemini/antigravity-cli/skills/agy-cli
     ```
   - 项目仓库级技能（Repository-level skills）：
     ```bash
     cp -r /path/to/agy-cli /path/to/project/.agents/skills/agy-cli
     ```

2. **赋予脚本执行权限**：
   ```bash
   chmod +x scripts/agy-run.sh
   ```

---

## 快速上手 (Quick Start)

这里准备了几个最常用的场景，复制粘贴就能跑起来：

### 1. 让 agy 帮你读代码、找问题（默认分析模式）
在默认的 plan 模式（`--write-level none`）下分析项目代码：

```bash
./scripts/agy-run.sh --cwd /path/to/project \
  'Explain the retry logic in src/client.ts and identify missing evidence.'
```

### 2. 需求较长？用 Heredoc 或管道传多行内容
遇到复杂的提示词，直接用带引号的 heredoc 或管道喂给它，脚本能自动识别：

```bash
./scripts/agy-run.sh --cwd /path/to/project <<'PROMPT'
Review src/orders/create.ts for race conditions and idempotency issues.
Report actionable findings with line numbers. Do not edit files or run shell commands.
PROMPT
```

### 3. 程序化调用：获取结构化 JSON 结果与退出码
如果你在写 Agent 代码或者自动化工作流，加上 `--json` 就能在标准输出拿到结构化结果，并根据退出码精准做容错：

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

> **小贴士（管道注意事项）：** 如果在脚本后面直接接管道（比如 `./scripts/agy-run.sh ... | jq ...`），记得在前面加上 `set -o pipefail` 或者像上面那样先暂存退出码，避免管道后面的命令把封装脚本的真实退出码掩盖掉。

---

## 选项参数一览 (Options)

`scripts/agy-run.sh` 支持以下参数：

| Option | Argument | Default | Description |
| --- | --- | --- | --- |
| `'PROMPT'` | String | 无（None） | 用引号包起来的位置参数提示词。只能传一个带引号的 prompt。如果 prompt 碰巧以 `-` 开头，请在前面加上 `--`。 |
| `--prompt-file` | `FILE` | 无（None） | 从文件 `FILE` 读取提示词；传入 `-` 表示从标准输入（stdin）读取。不可与位置参数 prompt 同时使用。省略时，prompt 来自位置参数或隐式的管道 / 文件 stdin。 |
| `--cwd` | `DIR` | 当前目录（`$PWD`） | `agy` 跑任务时的工作目录。 |
| `--model` | `ID` | 省略（Omitted） | 传递给 `agy` 的模型 ID（例如 `gemini-3.1-pro-low`）。 |
| `--effort` | `LEVEL` | 省略（Omitted） | 推理思考级别（Reasoning effort）：可选 `low`、`medium`、`high`、`xhigh` 或 `max`。若指定了 `--model claude-*` 则会被拒绝。 |
| `--write-level` | `LEVEL` | `none` | 执行权限档位：可选 `none`、`files` 或 `commands`。 |
| `--resume` | `ID` | 无（None） | 恢复已有会话（向 `agy` 传递 `--conversation ID`）。 |
| `--timeout` | `DUR` | `600s` | `agy` 输出超时时间（print timeout）。接受类似 `120s`、`2m`、`1m30s`、`0.5s`、`500ms` 的时长写法，写 `0` 表示不设超时。 |
| `--add-dir` | `DIR` | 无（None） | 允许 `agy` 额外访问的工作区目录，可重复指定以添加多个目录。 |
| `--json-schema` | `FILE` | 无（None） | 传入 JSON Schema 文件路径，让 `agy` 尽量按此结构返回（尽力而为，best-effort）。 |
| `--json` | 无（None） | `false` | 在 stdout 输出紧凑的单行 JSON 结果包（Version 2 结构）。 |
| `--include-raw` | 无（None） | `false` | 在 JSON 结果包中包含原始的 raw stdout 和 stderr（会自动开启 `--json`）。 |
| `-h`, `--help` | 无（None） | 无（None） | 显示使用帮助并退出（退出码 `0`）。 |

### 提示词输入规则与防呆机制 (Prompt Input Rules & Stdin Handling)

为了保证自动化调用不挂起、不卡死，脚本内置了严格的防呆规则：

1. **优先级（Precedence）**：命令行位置参数提示词或 `--prompt-file FILE` 优先级高于标准输入。不能同时传位置参数提示词和 `--prompt-file`。
2. **隐式 Stdin 智能检测（Implicit Stdin Detection）**：如果没传提示词参数，只有当 stdin 确实是管道（`-p /dev/stdin`）或常规文件/heredoc（`-f /dev/stdin`）时，脚本才会去读 stdin。
3. **交互式终端与死挂流防护（Interactive & Non-EOF Stream Protection）**：如果你直接在终端交互窗口敲命令却不给提示词，脚本会立即拒绝退出。对于外部工具传入的从不发送 EOF 的 open socket 或字符设备（例如 `/dev/null`），脚本会快速报错并退出（退出码 `64`，`usage_error`），绝不傻等，除非你明确写了 `--prompt-file -`。
4. **必须读到 EOF（EOF Requirement）**：从 stdin 读取输入必须读到 EOF 为止。脚本读取输入阶段不设超时，`--timeout` 仅用于限制 `agy` 运行阶段。
5. **提示词大小上限（Prompt Budget）**：提示词必须是非空白内容，且不能包含 NUL（`\0`）字节。提示词本身以及加上注入行为公约后的最终完整文本，必须分别小于 120,000 字节（适配 Linux 命令行参数限制）。

---

## 权限档位与安全须知 (Write Levels and Safety Caveats)

无论选择哪一档权限，脚本都会自动以 `--sandbox` 启动 `agy`，并在提示词开头注入一段英文行为公约（`<execution_contract>` 代码块），双重规范模型的行为。

| Write Level | `agy` Execution Mode | Injected Execution Contract |
| --- | --- | --- |
| `none` *(default)* | `--mode plan` | `Do not modify files or run shell commands. Analyze using permitted read tools or the supplied context. Report limitations only when they affect the requested task.`<br>（禁止修改文件或运行 shell 命令。使用允许的读取工具或所提供的上下文进行分析。仅在限制影响请求任务时报告限制。） |
| `files` | `--mode accept-edits` | `Edit files only within the requested scope. Do not run shell commands. Report changed files and any verification gaps relevant to the task.`<br>（仅在请求范围内编辑文件。禁止运行 shell 命令。报告更改的文件以及与任务相关的任何验证缺口。） |
| `commands` | `--mode accept-edits --dangerously-skip-permissions` | `Edit files and run commands only within the requested scope. Permission auto-approval does not authorize unrelated or destructive actions. Report changed files and actual verification.`<br>（仅在请求范围内编辑文件和运行命令。权限自动批准不代表授权无关或破坏性操作。报告更改的文件和实际验证结果。） |

### 安全注意事项 (Safety Caveats)

- **Plan 模式不是操作系统级的物理隔离（Plan Mode is Not an OS Boundary）**：在 `none` 模式下，`--mode plan` 和注入的行为公约属于强引导控制，提示模型不要动文件或跑命令。但这**不是**操作系统强制锁死的只读文件系统；如果有绝对只读的硬性要求，请在外部环境（如容器化或只读挂载）中做好隔离。
- **Commands 模式会自动批准所有权限（Commands Mode Auto-Approves All Permissions）**：`commands` 档位传递了 `--dangerously-skip-permissions`，这会把 `agy` 请求的**所有**工具权限全自动批准，并不只局限于 shell 执行。虽然 agy 内置沙箱依然有效，但放权范围很大。只有在任务明确授权了完整命令执行权限时，才应选择 `commands`。
- **严禁自动提权（No Automatic Privilege Escalation）**：如果任务因为权限不足被拒绝，你的主助手绝不能偷偷摸摸换到更高的 `--write-level` 重新跑。权限配置必须严格对齐任务本身的授权边界。

---

## 两种输出格式 (Output Formats)

### 1. 默认格式：纯文本模式 (Default (Text Mode))

适合直接把结果作为文本交给人类或主助手阅读：

- **标准输出（`stdout`）**：只有干净的模型回复文本（`.result.response`），保证末尾带有换行符。当回复为空或会话恢复失败时，`stdout` 保持为空。
- **标准错误（`stderr`）**：恰好一行、带 `agy-run: ` 前缀的单行 JSON 元数据诊断信息：

```text
agy-run: {"outcome":"ok","exit_code":0,"agy_exit_code":0,"conversation_id":"example-conversation-id"}
```

当发生错误或结果不是 `ok` 时，这行元数据中会自动补充诊断字段：
- `message`：对本次执行结果的简明文字说明。
- `error`：当底层 `result.error` 存在且不同于回复文本时填充。
- `stderr`：底层 CLI 报错诊断（会自动对 `result.error` 去重）。
- `raw_stdout`：如果底层输出的 JSON 格式损坏，这里会保留原始未解析的输出。

元数据中的换行符均已完成 JSON 转义，确保诊断信息始终保持在这一行上。

### 2. JSON 模式：`--json` 或 `--include-raw` (JSON Mode)

指定 `--json` 时，所有结果都将作为紧凑的单行 Version 2 JSON 结果包输出到 `stdout`，此时 `stderr` 保持为空：

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

字段解析（Envelope schema）：
- `version`：版本号，固定为整数 `2`。
- `outcome`：运行结论标识字符串（`ok`、`timeout`、`incomplete`、`agy_error` 或 `usage_error`）。
- `exit_code`：`agy-run.sh` 返回的整数退出码。
- `agy_exit_code`：`agy` 原始返回的整数退出码；若 `agy` 未执行则为 `null`。
- `message`：人类可读的结果说明摘要。
- `conversation_id`：当前活跃的会话 ID 字符串，或 `null`。
- `result`：从 `agy` 输出中解析出的完整 JSON 对象；如果不是合法 JSON 则为 `null`。
- `raw_stdout`：若传递了 `--include-raw`，或者 `result` 为 `null` 且原始 stdout 非空时包含此字段。
- `stderr`：若传递了 `--include-raw`，或者 CLI 的 stderr 非空时包含此字段。

---

## 退出码一览表 (Exit Codes)

`agy-run.sh` 规定了非常清晰的退出码，让你的自动化程序可以轻松分支处理：

| Exit Code | Outcome | Meaning & Conditions（含义与触发条件） |
| --- | --- | --- |
| **`0`** | `ok` | `agy` 正常返回了非空的 `SUCCESS` 状态且退出码为 `0`。<br>**注意：** 必须单独核查任务是否真正完成；如果模型在回答中婉拒了操作或答非所问，底层传输层面仍可能返回退出码 0。 |
| **`10`** | `timeout` | 发生 `agy` 输出超时（print timeout，通过 stderr 中的 `print timeout after` 或状态 `TIMEOUT` / `TIMED_OUT` 捕获）。输出内容可能不完整，且底层后台进程可能仍在继续运行。 |
| **`11`** | `incomplete` | 轮次结束但工作并未完成：记录了结构化的 `denied_actions`、stderr 输出了 `jetski: no output produced` 诊断信息，或者在没有超时的情况下回复内容为空 / 仅包含空白字符。 |
| **`12`** | `agy_error` | 运行时或底层 CLI 故障：`agy` 返回非零退出码、缺少依赖（`jq`、`agy`）、二进制文件不可执行、返回的结果 JSON 格式畸变、非成功状态或会话恢复失败。 |
| **`64`** | `usage_error` | 调用命令参数错误：缺少参数值、使用了未知选项、Claude 模型搭配了 `--effort`、超时格式不合法、提示词/Schema 文件不存在或超出大小限制、空白或含 NUL 字符的提示词，或在 TTY / 不受支持的流上遗漏了提示词。 |

---

## 多轮追问与恢复会话 (Resuming Conversations)

如果想接着之前的某次对话继续做，只需传入已知 `conversation_id` 的 `--resume <ID>`：

```bash
./scripts/agy-run.sh --cwd /path/to/project --resume "example-conversation-id" \
  --write-level files --prompt-file follow-up-fix.txt
```

### 会话完整性防坑守则 (Session Integrity Rules)

- **重新指定上下文（Re-apply Context）**：每个恢复轮次都必须明确重新指定对应的 `--cwd`、`--model` 以及该轮次授权的 `--write-level`。
- **自动防串话与会话漂移拦截（极关键）**：有时如果传了不存在的 ID，`agy` 会在 stderr 打印 `warning: conversation "..." not found`，然后悄悄开一个新会话并返回 0。为了防止助手误将新会话当成旧会话来处理：
  - `agy-run.sh` 会敏锐检测到该情况，并**立即终止，返回退出码 `12`（`agy_error`）**！
  - 在文本模式下，`stdout` 会被直接清空抑制，绝不让污染数据漏出；
  - 在 JSON 模式下，结果包中会保留详细诊断数据；
  - 此项安全检查的优先级高于超时判定。
- **绝不自动重试（No Automatic Retries）**：脚本每次只老老实实执行一次，绝不私自自动重试。一旦发生超时，在尝试恢复会话之前，务必先核实后台任务是否已执行完毕，以免造成重复执行的副作用。

---

## 已知限制与使用细节 (Known Limitations)

为了让你和助手用得更顺手，请了解以下客观边界：

- **超时机制是输出截止，非进程看门狗（`--timeout`，Timeout Behavior）**：
  `--timeout DUR`（默认 `600s`，设为 `0` 可关闭）设置的是 `agy` 的 `--print-timeout`。这是 CLI 打印输出的等待截止时间，**并不是**操作系统的进程看门狗（watchdog）。在输出超时时，`agy` 自身往往仍然以 `SUCCESS` 状态和退出码 0 退出；是咱们的脚本捕获超时并给出退出码 10。在 agy 打印出部分结果后，后台任务可能还在继续跑。
- **Plan 模式非操作系统物理沙箱（Plan Mode Not Enforced）**：
  `--write-level none` 会给 `agy` 传入 `--mode plan` 并注入公约指令。这属于 Agent 行为层面的引导约束，并不是操作系统底层的只读文件系统沙箱。
- **Linux 单参数约 128KB 限制（`ARG_MAX` / `MAX_ARG_STRLEN`）**：
  Linux 内核对单个命令行参数的尺寸限制约为 128 KiB（通常对应 32 个内存页）。如果把超长提示词直接放在命令行位置参数中，在脚本执行之前，Bash 本身就会报错并崩溃，提示 `Argument list too long`（退出码 `126`）。对于长提示词，请务必使用 `--prompt-file FILE` 或管道输入。脚本自身会对提示词强制执行 120,000 字节的安全预算上限。
- **`--json-schema` 属于尽力而为（`--json-schema` is Best Effort）**：
  `--json-schema FILE` 会将 schema 透传给 `agy`（`--json-schema "$schema"`），但大模型对 Schema 的遵循程度是尽力而为的。而且 Schema 仅用于约束 `.result.response` 的回复内容，并不影响脚本本身的 JSON 结果包。模型的回复中仍有可能掺杂闲聊文字、带代码块围栏的 markdown 或多余的键，调用方必须自行校验 `.result.response`。
- **Claude 模型拒绝 `--effort`（Claude Models Reject `--effort`）**：
  Claude 模型不支持 reasoning effort 思考级别。如果在指定 `--model claude-*` 的同时传入 `--effort`，脚本在参数校验阶段就会直接拦截，并退出且返回退出码 **`64`（`usage_error`）**。
- **无效的 Resume ID 会触发退出码 12（Invalid Resume ID Causes Exit 12）**：
  若给出的会话 ID 在底层不存在，`agy` 会静默开新会话；本脚本会识别到这一漂移并退出且返回退出码 **`12`（`agy_error`）**，同时抑制文本输出，避免把新会话误认作已恢复的会话。

---

## 运行测试 (Running Tests)

本项目内置了完整的单元测试，通过本地 mock 可执行文件测试参数解析、输入流识别、写入权限档位、超时捕获以及 JSON 序列化，完全不需要联网、不需要 API 密钥，也不需要事先安装 `agy`：

```bash
python3 -m unittest tests/test_agy_run.py
```

或者使用 unittest 的自动发现机制统一运行：

```bash
python3 -m unittest discover -s tests -v
```

> **注意（Note）：** 测试不需要网络访问、API 凭据或已安装的 `agy` 二进制文件；所有调用均针对本地 Python stub 运行。

---

## 许可证 (License)

本项目基于 MIT 许可证开源。
