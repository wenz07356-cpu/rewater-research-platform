# 再生水知识与深度研究平台 GitHub 仓库整理与发布方案

> 方案生成日期：2026-09-01
>
> 本地仓库：`E:\project\rewater-research-platform`
>
> 建议仓库名：`rewater-research-platform`
>
> 建议初始可见性：**Private（私有）**

## 执行状态（2026-09-01）

本方案的本地 Git 整理阶段已经执行：忽略规则已补齐，真实环境配置、本地依赖、
IDE 文件、日志、RAGAS 运行结果和无关个人技能已排除；示例配置已去除活动内网默认
地址；仓库治理文件和基础 CI 已补充。当前阶段只创建本地 Git 提交，未配置 remote，
未创建 GitHub 仓库，也未执行任何网络推送。

## 一、结论

本项目已经是 Git 仓库，现有 `master` 分支和提交历史可以保留，但当前状态不适合直接执行 `git add .` 或推送到 GitHub。发布前应先完成忽略规则、敏感信息、IDE 文件、运行日志和工作区改动的整理。

推荐按以下顺序执行：

1. 备份并确认当前业务代码改动；
2. 完善 `.gitignore`，确保虚拟环境、缓存、IDE 配置、日志、报告和真实 `.env` 不会入库；
3. 从 Git 索引中移除已经跟踪的 `.idea` 文件；
4. 审核三个 `.env.example`，只保留空值、明显占位值或明确标注的本地开发默认值；
5. 分批提交“仓库基础设施”和“业务代码改动”；
6. 运行测试、Compose 配置检查和敏感信息扫描；
7. 在 GitHub 创建私有空仓库，设置远程地址，将默认分支统一为 `main` 后首次推送；
8. 推送后启用分支保护、Secret scanning 和依赖更新能力。

## 二、当前仓库体检结果

### 2.1 Git 状态

- 本地 Git 仓库已存在，当前分支为 `master`。
- 当前提交为 `8e57365 feat: integrate municipal knowledge retrieval into research service`。
- 当前没有配置 Git remote，因此尚未连接 GitHub 仓库。
- Git 对该目录报告 `dubious ownership`。这是当前执行用户与目录所有者 SID 不一致导致的安全保护，不代表仓库损坏。
- 当前约有 233 个已跟踪文件；Git 对象包约 1.78 MiB，历史中暂未发现大文件问题。
- 当前工作区不是干净状态，至少包含：
  - 4 个业务文件修改；
  - 4 个 `knowledge-service/.idea` 文件删除；
  - 根 README、Compose、Dockerfile、脚本、部署配置和技能文件等未跟踪内容。

发布前必须逐项审阅这些变化，不能使用不加选择的“一次性提交”。

### 2.2 主要风险

| 级别 | 问题 | 影响 | 处理建议 |
| --- | --- | --- | --- |
| 高 | 根 `.gitignore` 仅包含 `.env`、`models/` | 容易误提交虚拟环境、缓存、IDE 文件和运行产物 | 发布前扩充根忽略规则 |
| 高 | 工作区存在真实 `.env` | 若强制添加或修改忽略规则，可能泄露 API Key 和基础设施凭据 | 永远不提交；推送前执行 `git check-ignore` 和秘密扫描 |
| 高 | `services` 工作区约 1.4 GiB，包含 `.venv`；发现最大约 252.7 MiB 的 PyTorch DLL | 直接添加会超过 GitHub 单文件限制并使仓库不可维护 | 忽略所有 `.venv/`，模型与二进制依赖通过安装/挂载获得 |
| 中 | 根 `.idea/`、`knowledge-service/.idea.backup/` 及已跟踪的服务级 `.idea` | 引入个人 IDE 状态和无意义冲突 | 全局忽略并从索引移除 |
| 中 | `services/rewater-agent-data-base/` 当前仅见运行日志 | 日志可能包含查询、错误上下文或内部地址 | 整个目录不发布，或仅保留说明文件 |
| 中 | 缺少 GitHub Actions、LICENSE、SECURITY、CONTRIBUTING 等治理文件 | 缺少自动检查及协作规则 | 私有首发可分阶段补齐；公开前必须决定许可证 |
| 中 | 目标 `text/` 目录当前被服务级 `.gitignore` 忽略 | 本方案文件默认无法入库 | 只放行 `text/research_888.md` |

### 2.3 敏感信息检查结论

- 当前根 `.env`、`knowledge-service/.env`、`research-service/.env` 均存在，但按现有规则处于忽略状态。
- 在当前可达 Git 历史中未发现路径名恰好为 `.env` 的已提交文件。
- 历史中存在 `.env.example` 提交，这是正常做法，但仍需审核其值。
- 根 `.env.example` 的密钥字段当前为空。
- `knowledge-service/.env.example` 含明显占位值和 `minioadmin` 本地开发默认值。它们不应被用于公网或生产环境，建议增加注释说明“仅限本地开发”。
- 仍建议把当前 `.env` 中出现过的真实第三方 Key 视为私密信息；如果曾通过聊天、日志、压缩包或其他仓库外渠道暴露，应在供应商控制台轮换。

## 三、建议的仓库边界

### 3.1 应提交

- 根目录：`README.md`、`.env.example`、`.gitignore`、Compose 文件；
- `deploy/`：Nginx 网关配置和静态入口；
- `scripts/`：启动、检查和停止脚本；
- `services/knowledge-service/`：应用源码、测试、依赖清单、Dockerfile、必要文档；
- `services/research-service/`：应用源码、测试、静态页面、依赖清单、Dockerfile、必要文档；
- `skill/`：仅在确认这些技能说明属于项目交付物、无内部敏感规则后提交；
- 本方案文件 `services/research-service/text/research_888.md`。

### 3.2 不应提交

- 所有真实 `.env`、Key、Token、证书和私钥；
- `.venv/`、`__pycache__/`、`*.pyc`、`*.egg-info/`；
- `.tmp/`、pytest/Ruff/mypy/coverage 缓存；
- `.idea/`、`.idea.backup/`、`.vscode/`；
- `models/` 及本地 BGE 模型权重；
- `logs/`、`*.log`、运行报告、数据库文件和对象存储数据；
- 本机绝对路径、用户查询数据、内部数据库导出；
- `services/rewater-agent-data-base/` 当前的日志内容。

## 四、建议修改项

### 4.1 扩充根 `.gitignore`

建议根规则至少包含：

```gitignore
# Secrets and local configuration
.env
.env.*
!.env.example
!**/.env.example
*.pem
*.key
*.p12
*.pfx

# Python
**/.venv/
**/venv/
**/__pycache__/
*.py[cod]
**/*.egg-info/
**/.pytest_cache/
**/.ruff_cache/
**/.mypy_cache/
.coverage
htmlcov/

# IDE and OS
**/.idea/
**/.idea.backup/
**/.vscode/
*.iml
.DS_Store
Thumbs.db

# Local artifacts
.tmp/
models/
**/logs/
*.log
**/reports/
services/rewater-agent-data-base/
```

注意：`.env.*` 会同时匹配 `.env.example`，因此后面的两个 `!` 放行规则不能遗漏。

### 4.2 只放行本方案文件

`services/research-service/.gitignore` 当前有一行 `text/`。若需要让本方案随仓库上传，应改为：

```gitignore
text/*
!text/research_888.md
```

这样只提交本方案，不会把该目录的其他研究过程文件一起上传。

### 4.3 清理已跟踪的 IDE 文件

完善忽略规则后，从 Git 索引移除已经跟踪的 IDE 配置。该操作不需要删除开发者本机文件：

```powershell
git rm -r --cached --ignore-unmatch services/knowledge-service/.idea
git rm -r --cached --ignore-unmatch services/research-service/.idea
```

`knowledge-service/.idea` 当前已有删除状态，提交这些删除即可；不要为了恢复 Git 状态而把 IDE 配置重新加入仓库。

### 4.4 补齐治理与自动化

建议首发至少补充：

- `.github/workflows/ci.yml`：分别安装两个服务的锁定依赖，运行 Ruff 和 pytest；
- `SECURITY.md`：说明漏洞与密钥泄露的私下报告渠道；
- `CONTRIBUTING.md`：说明分支、提交、测试和 PR 规则；
- `.gitattributes`：统一文本文件行尾，避免 Windows/Linux 换行噪音；
- `LICENSE`：仅在项目所有者明确授权公开源代码后选择。没有许可证不等于允许外部自由使用。

## 五、推荐实施步骤

以下命令均在仓库根目录执行。当前环境若持续遇到 `dubious ownership`，先由仓库实际所有者确认路径可信，再执行：

```powershell
git config --global --add safe.directory E:/project/rewater-research-platform
```

也可在单次命令中使用 `git -c safe.directory=E:/project/rewater-research-platform ...`，避免修改全局配置。

### 阶段 A：建立安全基线

```powershell
git status --short --branch
git diff --stat
git diff
git diff --cached
```

操作要求：

1. 确认 4 个业务文件修改确实属于本次发布；
2. 不覆盖或还原未知来源的现有改动；
3. 完善根和服务级 `.gitignore`；
4. 处理已跟踪 `.idea` 文件；
5. 检查忽略是否生效：

```powershell
git check-ignore -v .env
git check-ignore -v services/knowledge-service/.env
git check-ignore -v services/research-service/.env
git check-ignore -v services/knowledge-service/.venv
git check-ignore -v services/rewater-agent-data-base/logs/app_20260901.log
```

所有真实 `.env`、虚拟环境和日志都应显示命中的忽略规则。

### 阶段 B：分批暂存和审查

不要直接运行 `git add .`。推荐按逻辑分批：

```powershell
git add .gitignore .env.example README.md compose.yaml compose.local-infra.yaml
git add deploy scripts
git add services/knowledge-service/.dockerignore services/knowledge-service/Dockerfile
git add services/research-service/.dockerignore services/research-service/Dockerfile
git add skill
git add -f services/research-service/text/research_888.md
git status --short
git diff --cached --stat
git diff --cached
```

如果已经按 4.2 放行本文件，则最后一条可不用 `-f`。`skill/` 必须在人工审核后再添加。

建议将提交拆分为：

```text
chore(repo): add root deployment and repository hygiene
chore(repo): remove tracked IDE metadata
feat(knowledge): update import and chat application
feat(research): update research web interface
docs: add GitHub publication plan
```

拆分提交能让代码审查、回滚和问题定位更清楚。实际提交范围应以 `git diff` 为准。

### 阶段 C：验证

最低验证项：

```powershell
docker compose config
docker compose -f compose.yaml -f compose.local-infra.yaml config
```

然后分别在两个服务目录运行项目已有的 Ruff 和 pytest。考虑到部分测试可能依赖模型或外部服务，应先跑不依赖 MongoDB、Redis、LLM、模型下载的单元测试，再记录无法离线执行的集成测试。

提交前再次检查：

```powershell
git status --short
git ls-files | Select-String -Pattern '(^|/)(\.env|\.venv|\.idea|logs)(/|$)|\.log$'
git ls-files | ForEach-Object {
    if (Test-Path -LiteralPath $_) {
        $item = Get-Item -LiteralPath $_
        if ($item.Length -ge 50MB) { $item.FullName }
    }
}
```

再使用可信的秘密扫描工具检查当前工作树和完整历史，例如 Gitleaks。若扫描发现真实凭据，应先撤销/轮换凭据，再清理历史；仅删除当前版本中的值是不够的。

### 阶段 D：创建 GitHub 仓库并推送

建议先在 GitHub 组织或个人账号下创建一个**空的私有仓库**：不要预先生成 README、`.gitignore` 或 LICENSE，以避免首次推送产生无意义的合并冲突。

确认提交完成后：

```powershell
git branch -m master main
git remote add origin https://github.com/<OWNER>/rewater-research-platform.git
git remote -v
git push -u origin main
```

如果使用 SSH：

```powershell
git remote add origin git@github.com:<OWNER>/rewater-research-platform.git
git push -u origin main
```

如果 `origin` 已存在，不要再次 `add`，改用：

```powershell
git remote set-url origin <REMOTE_URL>
```

也可使用 GitHub CLI 创建私有仓库并推送：

```powershell
gh auth status
gh repo create <OWNER>/rewater-research-platform --private --source . --remote origin --push
```

创建仓库、修改 remote 和首次 push 都会改变外部状态，执行前必须确认 `<OWNER>`、仓库名和可见性。

## 六、GitHub 侧配置建议

首次推送成功后：

1. 将 `main` 设为默认分支；
2. 为 `main` 建立 ruleset：禁止直接强推、禁止删除、要求通过 PR 合并；
3. 要求 CI 检查通过后才能合并；
4. 启用 Secret scanning、Push protection 和依赖安全更新（以账号/组织套餐可用能力为准）；
5. 配置 CODEOWNERS，至少指定 `knowledge-service`、`research-service`、部署配置的负责人；
6. GitHub Actions 所需密钥放入 repository/environment secrets，禁止写回 Compose 或 `.env.example`；
7. 生产发布使用 GitHub Environment，并为生产环境增加审批；
8. 确认仓库成员仅有最小必要权限。

## 七、是否保留现有提交历史

推荐默认**保留现有历史**，因为目前历史较小且能说明两个服务的演进。如果项目准备公开，还应先审查历史中的：

- 内部地址、用户名、邮箱和业务数据；
- `.env.example` 中是否曾出现过真实凭据；
- 提交信息和文档中是否包含客户或内部项目名称；
- 第三方代码、模型、课件和素材是否拥有再分发权。

只有在历史包含不可公开信息、且已完成凭据轮换后，才考虑使用 `git filter-repo` 重写历史。历史重写会改变全部相关 commit ID，属于高风险操作，不应在未备份和未通知协作者时执行。

## 八、首发验收清单

- [ ] `git status` 可正常执行，工作树中的每项变化都已确认；
- [ ] 三个真实 `.env` 均未被跟踪；
- [ ] `.env.example` 不含真实 Key、Token、密码或生产地址；
- [ ] `.venv`、模型、缓存、IDE 文件、日志、报告均未被跟踪；
- [ ] 没有大于 50 MiB 的待提交文件；
- [ ] 已跟踪的 `.idea` 文件已从索引移除；
- [ ] `docker compose config` 检查通过；
- [ ] 两个服务的离线单元测试和 Ruff 检查通过，或失败原因已记录；
- [ ] README 能让新开发者按 `.env.example` 完成启动；
- [ ] 私有仓库的 OWNER、名称、成员权限已确认；
- [ ] `main` 已推送并设置保护规则；
- [ ] 首次克隆验证通过：新目录中能够按 README 完成配置和启动。

## 九、建议的最终决策

本次发布建议采用“**保留历史、私有首发、清理后分批提交、验证后推送**”的方案。当前最优先的三个动作是：

1. 完善忽略规则并只放行本方案文档；
2. 审阅工作区业务改动和 `.env.example`，移除已跟踪 IDE 配置；
3. 在本地完成 Compose、Ruff、pytest 和秘密扫描后，再创建 GitHub 私有仓库。

按此流程执行后，可以避免把约 1.4 GiB 的本地依赖、运行日志和真实凭据误上传，同时保留现有有价值的项目演进历史。
