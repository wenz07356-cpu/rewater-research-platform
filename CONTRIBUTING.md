# 贡献指南

## 开发流程

1. 从最新的 `main` 创建短生命周期分支；
2. 只提交与当前任务有关的文件；
3. 提交前检查暂存差异、敏感信息和大文件；
4. 运行受影响服务的 Ruff、pytest 及必要的 Compose 配置检查；
5. 通过 Pull Request 合并，说明行为变化、验证结果和剩余风险。

## 提交约定

提交信息建议采用 `type(scope): summary` 格式，例如：

```text
feat(research): add report progress endpoint
fix(knowledge): preserve retrieval source metadata
chore(repo): improve ignored file rules
docs: clarify local deployment
```

每个提交应保持单一目的，避免把格式化、生成产物和无关业务修改混在一起。

## 本地验证

根目录配置检查：

```powershell
docker compose config
docker compose -f compose.yaml -f compose.local-infra.yaml config
```

服务代码优先使用各自的 `.venv` 运行 Ruff 和 pytest。依赖 MongoDB、Redis、模型、LLM
或外部搜索的测试应明确标记为集成测试，不能把真实凭据写入测试代码。

## 禁止提交

- `.env`、密钥、Token、证书和生产地址；
- 虚拟环境、模型权重、缓存、IDE 配置和日志；
- 数据库、对象存储或用户研究内容的导出；
- 未确认再分发授权的第三方代码、数据、模型或素材。
