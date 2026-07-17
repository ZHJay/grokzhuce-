# Sub2API Grok 账号串行导入实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在服务器部署并运行一个可测试、可续跑、严格串行的 Grok SSO 账号导入器。

**架构：** L0 负责纯解析和数据契约，两个 L1 分别负责本地 Admin JWT 与 Sub2API HTTP，L2 编排串行导入，CLI 只处理参数和报告。所有敏感值只保留在内存，报告不含邮箱、密码、SSO 或 JWT。

**技术栈：** Python 3 标准库、`unittest`、Docker CLI、PostgreSQL `psql`、Sub2API Admin HTTP API。

---

## 文件结构

- `account_record.py`：L0 账号记录、解析和全量唯一性校验。
- `local_admin_auth.py`：L1 Docker/PostgreSQL 发现和短期 JWT 签发。
- `sub2api_client.py`：L1 HTTP JSON 客户端、Grok 分组解析、账号分页、单账号创建。
- `import_flow.py`：L2 串行导入、跳过、失败继续和脱敏结果。
- `import_grok_accounts.py`：CLI 边界、dry-run/apply 与报告写入。
- `tests/test_account_record.py`：解析和校验测试。
- `tests/test_local_admin_auth.py`：fingerprint/JWT 测试。
- `tests/test_sub2api_client.py`：请求契约测试。
- `tests/test_import_flow.py`：串行、幂等和脱敏测试。

### 任务 1：账号记录契约

**文件：**
- 创建：`account_record.py`
- 测试：`tests/test_account_record.py`

- [ ] **步骤 1：编写失败测试**

```python
class ParseAccountRecordsTest(unittest.TestCase):
    def test_parses_three_fields_and_preserves_name(self):
        records = parse_account_records(["a@example.com|secret|sso-token"])
        self.assertEqual(records[0].account_name, "a@example.com|secret")

    def test_rejects_duplicate_email(self):
        with self.assertRaises(RecordValidationError):
            parse_account_records(["a@example.com|one|sso-1", "A@example.com|two|sso-2"])
```

- [ ] **步骤 2：运行测试确认因模块缺失而失败**

运行：`python3 -m unittest tests.test_account_record -v`
预期：`ModuleNotFoundError: No module named 'account_record'`。

- [ ] **步骤 3：实现不可变 `AccountRecord` 和严格解析**

```python
@dataclass(frozen=True)
class AccountRecord:
    line_number: int
    email: str
    password: str
    sso: str

    @property
    def account_name(self) -> str:
        return f"{self.email}|{self.password}"
```

- [ ] **步骤 4：运行任务测试和全量测试**

运行：`python3 -m unittest tests.test_account_record -v && python3 -m unittest discover -s tests -v`
预期：全部通过。

### 任务 2：本地 Admin JWT

**文件：**
- 创建：`local_admin_auth.py`
- 测试：`tests/test_local_admin_auth.py`

- [ ] **步骤 1：先测试 fingerprint 和 JWT**

```python
def test_resolve_token_version_matches_sub2api_rule(self):
    material = "admin@example.com\n$2a$10$hash"
    expected = int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big") & 0x7fffffffffffffff
    self.assertEqual(resolve_token_version("Admin@Example.com", "$2a$10$hash"), expected)
```

- [ ] **步骤 2：运行并确认因模块缺失失败**

运行：`python3 -m unittest tests.test_local_admin_auth -v`
预期：模块缺失失败。

- [ ] **步骤 3：实现 Docker 环境读取、固定 SQL 管理员查询和 15 分钟 HS256 JWT**

JWT payload 固定包含：`user_id`、`email`、`role`、`token_version`、`iat`、`nbf`、`exp`。子进程使用 argv 数组，不拼接敏感 shell 命令。

- [ ] **步骤 4：验证测试**

运行：`python3 -m unittest tests.test_local_admin_auth -v`
预期：全部通过，stdout 不含测试 secret。

### 任务 3：Sub2API HTTP 积木

**文件：**
- 创建：`sub2api_client.py`
- 测试：`tests/test_sub2api_client.py`

- [ ] **步骤 1：测试单账号 payload 和分页行为**

```python
def test_create_payload_contains_exactly_one_sso(self):
    client = RecordingClient()
    client.create_grok_from_sso(record, group_id=3)
    self.assertEqual(client.last_payload["sso_tokens"], ["sso-token"])
    self.assertEqual(client.last_payload["name"], "a@example.com|secret")
    self.assertEqual(client.last_payload["group_ids"], [3])
    self.assertIsNone(client.last_payload["expires_at"])
```

- [ ] **步骤 2：运行并确认失败**

运行：`python3 -m unittest tests.test_sub2api_client -v`
预期：模块缺失失败。

- [ ] **步骤 3：实现 JSON request、唯一 Grok 分组解析、分页账号读取和单账号创建**

创建 payload 固定包含 `credentials: {}`、`concurrency: 10`、`priority: 1`、`rate_multiplier: 1`、`expires_at: null`、`auto_pause_on_expired: false`。

- [ ] **步骤 4：验证任务测试**

运行：`python3 -m unittest tests.test_sub2api_client -v`
预期：全部通过。

### 任务 4：串行导入流程与 CLI

**文件：**
- 创建：`import_flow.py`
- 创建：`import_grok_accounts.py`
- 测试：`tests/test_import_flow.py`

- [ ] **步骤 1：测试调用序列、跳过和失败继续**

```python
def test_flow_never_starts_next_create_before_previous_returns(self):
    client = SequentialProbeClient()
    result = run_import(records, client, group_id=3, existing_names=set())
    self.assertEqual(client.events, ["start:1", "end:1", "start:2", "end:2"])
    self.assertEqual(result.created, 2)
```

- [ ] **步骤 2：运行并确认失败**

运行：`python3 -m unittest tests.test_import_flow -v`
预期：模块缺失失败。

- [ ] **步骤 3：实现同步 for-loop、脱敏结果和 CLI**

CLI 参数为：`input_file`、`--dry-run`、`--apply`、`--base-url`、`--report`。`--dry-run` 和 `--apply` 互斥；apply 失败数大于 0 时退出码为 2。

- [ ] **步骤 4：运行完整测试和语法检查**

运行：`python3 -m compileall -q . && python3 -m unittest discover -s tests -v`
预期：语法检查退出 0，全部测试通过。

### 任务 5：部署、dry-run、apply 与交叉核验

**文件：**
- 部署目录：`/home/ubuntu/sub2api-grok-importer/`
- 私密输入：`/home/ubuntu/sub2api-grok-importer/private/grok_accounts.txt`，权限 `600`
- 报告：`/home/ubuntu/sub2api-grok-importer/reports/import-20260717.json`

- [ ] **步骤 1：上传代码和输入，设置权限**

运行：`scp` 上传代码；服务器执行 `chmod 600 private/grok_accounts.txt`。

- [ ] **步骤 2：服务器完整测试**

运行：`python3 -m compileall -q . && python3 -m unittest discover -s tests -v`
预期：全部通过。

- [ ] **步骤 3：真实 dry-run**

运行：`python3 import_grok_accounts.py private/grok_accounts.txt --dry-run`
预期：100 条有效记录；JWT 鉴权成功；解析到唯一 Grok 分组；创建调用数为 0。

- [ ] **步骤 4：记录导入前数据库基线并 apply**

运行：`python3 import_grok_accounts.py private/grok_accounts.txt --apply --report reports/import-20260717.json`
预期：严格逐条输出行号状态，末尾 created/skipped/failed 合计为 100。

- [ ] **步骤 5：API 与数据库交叉核验**

固定验证：
- 新账号均为 `platform='grok'`、`type='oauth'`；
- 均绑定分组 3；
- `expires_at IS NULL`；
- 本次输入生成的 100 个账号名称均存在且无重复；
- 报告不含 `@`、`|`、SSO、password、JWT。

- [ ] **步骤 6：提交最终代码**

运行：`git add . && git commit -m "feat: add serial Grok SSO account importer"`。
