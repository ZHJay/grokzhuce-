# 注册输出与 Sub2API 导入文档设计

**日期：** 2026-07-17

## 目标

让新用户从 `grok.py` 注册成功开始，能够只按照 README 完成账号文件生成、服务器准备、dry-run、严格串行导入、报告检查和安全续跑。

## 决策

1. `grok.py` 的输出文件名保持 `keys/grok_<时间戳>_<数量>.txt` 不变。
2. 每条成功记录由仅写入 SSO 改为 `email|password|sso`。
3. 格式化规则放在 L0 公理层 `account_record.py`，注册端与 importer 共用同一输入契约。
4. 私密追加写入放在 L1 积木层 `account_output.py`；Unix 创建或重开文件时强制 `0600`，且拒绝跟随 symlink。
5. README 把“导入到 Sub2API”作为一级主章节，放在注册输出说明之后、普通输出示例之前。

## README 用户路径

1. 完成注册并确认三字段账号文件。
2. 确认 Sub2API 服务器满足容器名称、Python、loopback API 和 sudo Docker 条件。
3. 在服务器 clone 仓库，通过 SSH 写入 `0600` 随机临时文件并原子替换输入文件。
4. Dry-run 分页读取全部平台账号，防止其他平台同名对象绕过幂等检查。
5. 先执行 `--dry-run`，只验证输入、管理员认证、Grok 分组和现有账号快照。
6. 再执行 `--apply --report ...`，严格串行导入。
7. 根据退出码、进度和脱敏 JSON 报告判断结果。
8. 仅 `failed=0` 可直接续跑；非合规创建或结果未知必须先按报告和服务端状态人工恢复。

## 安全边界

- 示例只使用占位主机、路径和域名。
- 明确说明账号名称为 `email|password`，密码会出现在 Sub2API 账号名称及数据库中。
- 输入文件、`.env`、报告、JWT、Cookie 和 SSH 凭据不得提交到 Git。
- Solver 示例必须显式绑定 `127.0.0.1`，注册输出在 Unix 上强制为 `0600`。
- Importer 通过 `lstat`、`O_NOFOLLOW`、`fstat` 和 mode 检查拒绝不安全输入。
- HTTP 默认只使用服务器 loopback；HTTPS 以外的远程 origin 会被拒绝。

## 验证

- 先用失败测试证明三字段格式化能力尚不存在，并覆盖真实文件 `splitlines()` 对 CR/LF 的处理，再实现并运行完整测试。
- 运行 `python3 import_grok_accounts.py --help` 核对 README 参数。
- 扫描 README，确认没有私人 IP、邮箱、token、密码、密钥路径或真实账号数据。
- 检查 Markdown 围栏、标题层级、内部文件引用和示例命令。
