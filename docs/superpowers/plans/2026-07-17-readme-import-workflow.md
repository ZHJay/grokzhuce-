# 注册输出与 Sub2API 导入 README 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让注册输出直接符合 importer 契约，并提供一套可复制执行的 Sub2API 导入说明。

**架构：** `account_record.py` 继续作为 L0 公理层，新增三字段序列化函数；`grok.py` 只调用该契约，不新增格式规则。README 以注册→上传→dry-run→apply→报告→续跑为主路径，所有示例保持脱敏。

**技术栈：** Python 3 标准库、`unittest`、Markdown、Git。

---

## 文件结构

- 修改 `account_record.py`：新增 `format_account_record` 三字段序列化契约。
- 修改 `grok.py`：注册成功时写入完整三字段记录。
- 修改 `tests/test_account_record.py`：覆盖精确输出与歧义分隔符拒绝。
- 修改 `README.md`：新增端到端 import 主章节，并更新功能、结构和输出说明。
- 修改 `.gitignore`：忽略 README 导入流程创建的 `private/` 和 `reports/`。

### 任务 1：共享注册输出契约

**文件：**
- 修改：`tests/test_account_record.py`
- 修改：`account_record.py`

- [ ] **步骤 1：编写失败测试**

```python
from account_record import format_account_record


def test_formats_registration_output_for_importer():
    assert format_account_record(
        "user@example.com", "password123", "sso-token"
    ) == "user@example.com|password123|sso-token"


def test_rejects_ambiguous_registration_output():
    with pytest.raises(RecordValidationError):
        format_account_record("user@example.com", "pass|word", "sso-token")
```

实际仓库使用 `unittest`，实现时将断言写成现有 `TestCase` 风格。

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python3 -m unittest tests.test_account_record -v
```

预期：导入 `format_account_record` 失败，因为函数尚不存在。

- [ ] **步骤 3：实现最少序列化契约**

```python
def format_account_record(email: str, password: str, sso: str) -> str:
    line = f"{email}|{password}|{sso}"
    parsed = parse_account_records([line])[0]
    if (parsed.email, parsed.password, parsed.sso) != (email, password, sso):
        raise RecordValidationError("record fields cannot round-trip safely")
    return line
```

- [ ] **步骤 4：运行测试验证通过**

```bash
python3 -m unittest tests.test_account_record -v
```

预期：全部通过。

### 任务 2：注册程序写入完整账号记录

**文件：**
- 修改：`grok.py:1-10,255-270`

- [ ] **步骤 1：接入共享契约**

```python
from account_record import format_account_record
```

- [ ] **步骤 2：替换成功写入逻辑**

```python
record_line = format_account_record(email, password, sso)
with open(output_file, "a", encoding="utf-8") as output:
    output.write(record_line + "\n")
```

保持现有 `file_lock`、失败清理和成功计数逻辑不变。

- [ ] **步骤 3：执行语法与完整回归测试**

```bash
python3 -m compileall -q account_record.py grok.py
python3 -m unittest discover -s tests -v
```

预期：语法检查通过，完整测试无失败。

### 任务 3：重写 README 导入路径

**文件：**
- 修改：`README.md`
- 修改：`.gitignore`

- [ ] **步骤 1：更新功能和项目结构**

补充三字段安全输出、严格串行 Sub2API importer 及相关模块。

- [ ] **步骤 2：新增“导入到 Sub2API”一级章节**

章节必须按以下顺序：

1. 输入格式与安全警告；
2. 前置条件；
3. 注册并确认文件；
4. 在服务器 clone 与上传；
5. `chmod 600`；
6. `--dry-run`；
7. `--apply --report`；
8. 输出、退出码和报告；
9. 幂等续跑；
10. 常见错误和安全清单。

- [ ] **步骤 3：核对 CLI**

```bash
python3 import_grok_accounts.py --help
```

README 只能使用真实存在的 `input_file`、`--dry-run`、`--apply`、`--base-url` 和 `--report` 参数。

- [ ] **步骤 4：安全与 Markdown 验证**

将 `private/` 和 `reports/` 加入 `.gitignore`，再执行：

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q account_record.py grok.py import_grok_accounts.py
```

另外检查 README 不含私人 IP、真实邮箱、SSO、JWT、密码、密钥路径或账号文件内容，并执行 `git diff --check`。

### 任务 4：提交与发布决策

- [ ] **步骤 1：检查最终 diff**

```bash
git status --short
git diff --check
git diff -- README.md account_record.py grok.py tests/test_account_record.py
```

- [ ] **步骤 2：提交**

```bash
git add README.md account_record.py grok.py tests/test_account_record.py \
  docs/superpowers/specs/2026-07-17-readme-import-workflow-design.md \
  docs/superpowers/plans/2026-07-17-readme-import-workflow.md
git commit -m "docs: add end-to-end Sub2API import guide"
```

- [ ] **步骤 3：等待用户确认后推送**

未获得明确 push 指令时只保留本地 commit；获得确认后 fast-forward 合并到 `main` 并推送 `origin/main`。
