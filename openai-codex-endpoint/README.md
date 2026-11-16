# openai-codex-endpoint

让 OMP 的 `openai-codex` provider 走 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)（CPA），同时保留 OMP 对 `openai-codex` 的内置策略（提示缓存、Codex 定价与服务档位、上下文上限、`apply_patch` 等）。

## 功能

- **地址切换**：环境变量 `CODEX_CPA_BASE_URL` 非空时，覆盖 `openai-codex` 的运行时地址，首个请求即生效；不写回配置，不改认证。未设置时使用 `models.yml` 中的地址。
- **模型发现**：OMP 原生 Codex 发现请求 `{baseUrl}/codex/models` 与 `{baseUrl}/models`，CPA 不提供这两个路由，新模型因此不会出现。本扩展改从 CPA 的 `{CPA 根地址}/v1/models?client_version=...` 读取 Codex 格式的模型目录，用 OMP 自带的 Codex 目录解析器注册到 `openai-codex` 下。
  - 只注册 `gpt-` 开头且未隐藏的模型；其他模型（如 DeepSeek、GLM）应通过 OpenAI 兼容 provider 使用。
  - 推理请求仍发往同一 CPA 的 `/backend-api`。
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

新模型首次出现前，执行 `omp models refresh`。

## 限制

- 模型列表缓存 24 小时，缓存只按 provider 区分、不区分地址：切换到另一个 CPA 后，需执行 `omp models refresh` 才会立即换成该 CPA 的列表。
- OMP 原生 Codex 发现仍会向 CPA 请求上述两个路由并得到 404，然后沿用它自己的旧缓存；旧缓存里 CPA 并不提供的模型可能继续留在列表中。
- `omp --model` 在扩展加载前解析，写成 `--model openai-codex/<模型>:low` 这种带思考档位后缀的形式会直接报“未找到”；改用 `--model openai-codex/<模型> --thinking low`。配置文件中的模型角色不受影响。
- 依赖 OMP 内部模块 `@oh-my-pi/pi-catalog/discovery/codex` 与 `@oh-my-pi/pi-catalog/wire/codex`，已验证版本见仓库 README。
