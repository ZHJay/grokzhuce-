# Sub2API Grok 账号串行导入设计

## 目标

将 `grok_20260717_143940_100_accounts.txt` 中的 100 条 `email|password|sso` 记录写入服务器上的 Sub2API。每次请求只导入一个账号，账号名称为 `email|password`，平台为 Grok，类型为 OAuth，绑定名称为 `Grok` 且平台为 `grok` 的分组，不设置运营侧过期时间，并通过 SSO Cookie 转换接口创建账号。

## 已验证上下文

- 输入文件有 100 条非空记录，均为 3 个字段；邮箱和 SSO 均唯一。
- 服务器 Sub2API 镜像版本为 `0.1.156`，revision 为 `12f991dde8a58e183d4bd16a87ef6fd0df714757`。
- 官方接口为 `POST /api/v1/admin/grok/sso-to-oauth`。
- 当请求仅包含一个 SSO 时，后端 worker 数为 1。
- 服务器存在 `Grok` 分组，当前 ID 为 3；脚本仍会按名称和平台动态解析，不硬编码 ID。
- 当前容器没有可用的 `ADMIN_PASSWORD`，数据库也未配置永久 Admin API Key。

## 架构

- **L0 公理层 `account_record.py`：** 定义账号记录并严格解析 `email|password|sso`。分隔时最多切两次，避免 SSO 内未来出现分隔符时破坏字段。
- **L1 积木层 `local_admin_auth.py`：** 读取 Docker 容器环境和管理员数据库记录，按运行版本的 token-version fingerprint 规则签发 15 分钟 HS256 JWT。JWT、JWT secret 和密码哈希只存在内存，不写日志或文件。
- **L1 积木层 `sub2api_client.py`：** 封装分组查询、账号分页查询和单账号 SSO 导入。
- **L2 流程层 `import_flow.py`：** 逐条串行导入、精确名称去重、失败继续、脱敏结果汇总。
- **CLI 边界 `import_grok_accounts.py`：** 参数解析、dry-run/apply 门控、报告输出和退出码。

没有跨多个业务模块的协调，因此不创建 L3 外交层。

## 数据流

1. 读取输入并完成全量格式校验；任何格式错误都阻止 apply。
2. 生成短期本地 Admin JWT，并调用 `/admin/groups/all?platform=grok` 解析唯一 `Grok` 分组。
3. 分页读取现有 Grok 账号名称，构建去重集合。
4. 对每条记录：
   - 名称为 `email|password`；
   - 若精确名称已存在则跳过；
   - 向 `/admin/grok/sso-to-oauth` 发送单元素 `sso_tokens`；
   - `group_ids` 只含 Grok 分组；
   - `credentials` 为空，表示 UI 的 whitelist 模式未指定模型，即支持全部模型；
   - `expires_at=null`、`auto_pause_on_expired=false`；
   - 等待当前响应后才处理下一条。
5. 输出只含行号、状态、account ID 和经过净化的错误，不输出账号名称、邮箱、密码、SSO、JWT 或密码哈希。

## 幂等与恢复

- 每次启动从 Sub2API 读取现有 Grok 账号名称。
- 精确名称已存在的记录标记为 skipped，不再次转换 SSO。
- 成功创建后立即加入内存集合；进程中断后重跑仍会从服务端状态恢复。

## 错误处理

- 文件解析、认证、分组不唯一等前置错误：立即停止，不创建任何账号。
- 单账号转换或创建失败：记录脱敏错误并继续下一条。
- HTTP 超时：记录失败，不自动重试，避免上游已创建但响应丢失造成重复；重跑时由服务端名称去重。
- 最终只要存在失败，CLI 返回非零退出码。

## 测试与验证

- parser：正常记录、缺字段、空字段、重复邮箱/SSO。
- auth：token-version fingerprint、HS256 JWT payload 与签名。
- client：单元素 SSO payload、分组解析、分页账号读取、HTTP 错误净化。
- flow：严格串行、存在账号跳过、部分失败继续、敏感字段不进入报告。
- dry-run：在服务器解析真实文件并验证认证、分组和现有账号读取，不调用创建接口。
- apply 后：API 和数据库交叉核验新增账号的平台、OAuth 类型、Grok 分组、名称集合及 `expires_at`。