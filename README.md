# Grok 批量注册与 Sub2API 导入工具

本项目包含两条完整流程：

1. 批量注册 Grok 账号，并自动开启 NSFW / Unhinged 模式；
2. 将注册结果通过 Sub2API 管理 API **严格串行**导入为 Grok OAuth 账号。

> [!IMPORTANT]
> 注册结果包含邮箱、明文密码和 SSO Cookie。请将 `keys/`、`private/`、`reports/` 和 `.env` 视为敏感数据，禁止提交到 Git 或发送到不受信任的主机。

## 功能

- 自动创建临时邮箱、获取验证码并完成 Grok 注册
- 自动开启 NSFW / Unhinged 模式
- 支持本地 Turnstile Solver 或 YesCaptcha
- 输出可直接交给 importer 的 `email|password|sso` 文件
- 通过 Sub2API 管理 API 严格串行导入，一次只转换和创建一个账号
- 导入前支持 dry-run；长批次自动刷新短期管理员 JWT
- 按完整后置条件幂等续跑，并生成不含账号凭据的私密 JSON 报告

## 一、注册 Grok 账号

### 1. 安装依赖

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中填写必需的 `MAIL_BASE_URL`、`MAIL_ADMIN_PASSWORD`、`MAIL_DOMAIN`；按需填写 `MAIL_SITE_PASSWORD` 和 `YESCAPTCHA_KEY`。字段说明见 `.env.example`。

### 2. 启动 Turnstile Solver

未配置 `YESCAPTCHA_KEY` 时执行：

```bash
python3 api_solver.py --host 127.0.0.1 --browser_type camoufox --thread 5 --debug
```

该命令显式限制 Solver 监听 `http://127.0.0.1:5072`。Windows 也可双击 `TurnstileSolver.bat`。

### 3. 运行注册程序

新开一个终端：

```bash
python3 grok.py
```

按提示输入并发数和注册数量。成功记录写入：

```text
keys/grok_<时间戳>_<数量>.txt
```

文件中每行严格为：

```text
email|password|sso
```

不要手工改变字段顺序，也不要在 SSO 中加入逗号或换行。

## 二、导入到 Sub2API（重点）

### 导入结果

每条输入会创建一个满足以下设置的账号：

| 字段 | 值 |
|---|---|
| 账号名称 | `email|password` |
| 平台 / 类型 | `grok` / `oauth` |
| 分组 | 名称为 `Grok`、平台为 `grok` 的唯一启用分组 |
| 并发 / 优先级 /倍率 | `10` / `1` / `1` |
| 过期时间 | 不设置；关闭过期自动暂停 |
| 模型映射 | 不设置额外映射 |

> [!WARNING]
> 按当前导入契约，**明文密码会出现在 Sub2API 账号名称及数据库中**。若这不符合你的安全要求，请先修改 `AccountRecord.account_name` 和对应测试，再导入。

### 1. 确认服务器前置条件

Importer 应在 Sub2API 所在服务器运行，并要求：

- Python 3.10+；importer 本身只使用标准库；
- Docker daemon 正在运行，当前用户可以执行 `sudo docker`；
- Sub2API 容器名为 `sub2api`；PostgreSQL 容器名为 `sub2api-postgres`；
- Sub2API API 默认监听 `http://127.0.0.1:8080/api/v1`；
- 数据库内至少存在一个 active admin；
- 存在唯一的 active `Grok` / `grok` 分组；接口契约按 Sub2API `v0.1.156`（revision `12f991d`）核对，其他版本必须先通过 dry-run 验证。

在服务器检查：

```bash
python3 --version
sudo docker ps --format '{{.Names}}'
```

### 2. 在服务器获取代码

```bash
git clone https://github.com/ZHJay/grokzhuce-.git ~/grokzhuce
cd ~/grokzhuce
mkdir -p private reports
```

如果已经 clone：

```bash
cd ~/grokzhuce
git pull --ff-only
```

### 3. 上传注册结果

在运行注册程序的电脑执行。数据通过 SSH 写入同目录 `0600` 随机临时文件，成功后原子替换最终文件：

```bash
ssh user@server '
  set -eu; umask 077; cd ~/grokzhuce; mkdir -p private
  tmp=$(mktemp private/.grok_accounts.XXXXXX)
  trap "rm -f \"$tmp\"" EXIT
  cat >"$tmp"; chmod 600 "$tmp"
  mv -f "$tmp" private/grok_accounts.txt
  trap - EXIT
' < keys/grok_20260717_120000_100.txt
```

### 4. 先运行 dry-run

```bash
python3 import_grok_accounts.py \
  private/grok_accounts.txt \
  --dry-run
```

Dry-run 会在任何创建请求前完成：

- 拒绝 symlink、非普通或 Unix 非 `0600` 输入，并全量校验三字段、邮箱和 SSO 唯一性；
- 获取当前有效的本地管理员材料；
- 解析唯一的 Grok 分组；
- 分页读取全部平台的现有账号快照；
- 输出 `create_calls=0`，不会导入账号。

### 5. 正式严格串行导入

确认 dry-run 成功后执行：

```bash
python3 import_grok_accounts.py \
  private/grok_accounts.txt \
  --apply \
  --report "reports/import-$(date +%Y%m%d-%H%M%S).json"
```

流程始终按“转换一条 SSO → 创建一条账号 → 完成后处理下一条”执行，不使用并发。单条失败会记录为 `failed` 并继续下一条；前置条件失败则在任何创建前终止。

进度和汇总示例：

```text
[001/100] line=1 created account_id=501
[002/100] line=2 skipped account_id=502
summary total=100 created=95 skipped=5 failed=0
```

### 6. 查看退出码和报告

| 退出码 | 含义 |
|---:|---|
| `0` | dry-run 成功，或 apply 没有失败项 |
| `1` | 运行时 fatal；可能在 apply 已创建部分账号后发生，例如报告写入失败 |
| `2` | apply 至少一项失败，或 CLI 参数/用法错误（argparse） |

报告文件默认权限为 `600`，只包含行号、状态、账号 ID 和脱敏错误，不包含邮箱、密码、SSO 或 JWT。

### 7. 安全续跑

只有 `failed=0` 的完成批次可直接重复运行。若失败项带 `account_id`，表示服务端已创建但后置条件不合规，必须先按 ID 修复或删除；若发生 timeout/disconnect 等结果未知错误，必须先在 Sub2API 核验实际状态，不能盲目重试。

重新执行时会读取全部平台的账号；只有唯一同名且完整满足名称、平台、OAuth 类型、Grok 分组、模型映射、并发、优先级、倍率和过期设置的账号会被 `skipped`，其他同名状态会 `failed`。

## 常见问题

- `docker inspect ... non-zero exit status`：确认 Docker daemon、sudo 权限和两个容器名。
- `expected one active admin database row`：确认数据库存在 active admin，且没有误连其他部署。
- `expected exactly one active Grok group`：在 Sub2API 中保留唯一的 active `Grok` / `grok` 分组。
- `pagination metadata is invalid`：服务端账号列表响应与当前 importer 契约不兼容，先确认 Sub2API 版本和代理响应。
- `Grok SSO conversion failed`：检查对应 SSO 是否仍有效；报告不会保存上游敏感正文。
- 自定义 API 地址：使用 `--base-url URL`。明文 HTTP 只允许 loopback；远程地址必须使用 HTTPS。
- 查看全部参数：`python3 import_grok_accounts.py --help`。

## 安全清单

1. 不要提交 `.env`、`keys/`、`private/`、`reports/`、SSH 私钥或数据库凭据。
2. 不要把真实账号内容粘贴到 Issue、日志或聊天中。
3. Unix 上注册输出、输入和报告保持 `600`；Windows 上使用目录 ACL 保护 `keys/`。
4. Importer 使用服务器本地短期管理员 JWT，只保存在内存中，并会在长批次中提前刷新。
5. 凭据请求禁用环境代理和自动重定向，避免 Authorization 或 SSO 泄漏到其他 origin。
