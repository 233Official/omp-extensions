# openai-codex-endpoint

让 OMP 的 `openai-codex` provider 走 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)（CPA），同时保留 OMP 对 `openai-codex` 的内置策略（提示缓存、Codex 定价与服务档位、上下文上限、`apply_patch` 等）。

## 功能

- **地址切换**：环境变量 `CODEX_CPA_BASE_URL` 非空时，覆盖 `openai-codex` 的运行时地址，首个请求即生效；不写回配置，不改认证。未设置时使用 `models.yml` 中的地址。
- **模型发现**：OMP 原生 Codex 发现请求 `{baseUrl}/codex/models` 与 `{baseUrl}/models`，CPA 不提供这两个路由，新模型因此不会出现。本扩展改从 CPA 的 `{CPA 根地址}/v1/models?client_version=...` 读取 Codex 格式的模型目录，用 OMP 自带的 Codex 目录解析器注册到 `openai-codex` 下。
  - 只注册 `gpt-` 开头且未隐藏的模型；其他模型（如 DeepSeek、GLM）应通过 OpenAI 兼容 provider 使用。
  - 推理请求仍发往同一 CPA 的 `/backend-api`。OMP 保留目录声明的服务档位；对声明 `ultrafast` 的模型可用 `/fast ultra`。
  - 发现失败时报错并保留上次的模型缓存，不会清空列表。

以下情况扩展不生效，OMP 保持原生行为：未配置地址、地址是官方 `chatgpt.com`；地址不以 `/backend-api` 结尾时记录警告后跳过。

## 配置

`~/.omp/agent/models.yml`：

```yaml
providers:
  openai-codex:
    baseUrl: http://localhost:8317/backend-api   # CPA 地址 + /backend-api
    auth: apiKey
    apiKey: CPA_API_KEY                          # 存放 CPA API Key 的环境变量名
```

在多个 CPA 间切换时，在启动 OMP 前设置环境变量：

```bash
CODEX_CPA_BASE_URL=https://cpa.example.com/backend-api omp
```

新会话会自动发现模型。OMP 19.1.1 的独立 `omp models refresh` 不经过该发现钩子，不能用来检查 CPA 的目录。

## 限制

- 需要 OMP 19.1.0 或更新版本。扩展通过内置 provider 的 `discoverModels` 替换目录请求，缓存由 OMP 按 CPA 地址隔离。
- 使用 `auth: apiKey` 配置 CPA 凭据。要同时使用官方 Codex OAuth，使用单独的 OMP profile，不要与 CPA 共用同一 provider 的认证状态。
- `omp --model` 在扩展加载前解析，写成 `--model openai-codex/<模型>:low` 这种带思考档位后缀的形式会直接报“未找到”；改用 `--model openai-codex/<模型> --thinking low`。配置文件中的模型角色不受影响。
- `registerProvider().discoverModels` 是 OMP 扩展接口；Codex 目录解析和端点识别仍依赖 OMP 的内部模块。升级 OMP 时先检查仓库中的类型检查和加载测试。
