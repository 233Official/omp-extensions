# omp-extensions

轻量 [OMP（oh-my-pi）](https://github.com/can1357/oh-my-pi) 扩展合集。每个扩展一个目录，仓库根目录的 `package.json` 把它们作为一个 OMP 插件发布。体量较大、需要独立发版的扩展另建仓库。

| 扩展 | 说明 |
| --- | --- |
| [openai-codex-endpoint](openai-codex-endpoint/README.md) | 让 `openai-codex` provider 走 CLIProxyAPI（CPA）：按环境变量切换地址，并从 CPA 发现 Codex 模型 |

## 安装与更新

```bash
omp plugin install github:233Official/omp-extensions
omp plugin upgrade omp-extensions
```

安装后新开 OMP 进程生效。各扩展的配置见其目录下的 README。

已验证版本：OMP 18.20.3，CLIProxyAPI v8.0.73。扩展使用了 OMP 的内部模块，其他 OMP 版本可能无法加载；出现问题时请附 `omp --version` 提交 Issue。

## 开发

### 目录结构

```text
package.json                 插件清单：omp.extensions 列出各扩展目录
<扩展>/package.json           扩展清单：omp.extensions 指向入口文件
<扩展>/index.ts               扩展入口
scripts/sync_omp_extension.py 本机同步工具（macOS）
tests/                        同步工具回归测试与真实 OMP 加载测试
```

扩展目录保持扁平：同步只复制目录第一层的普通文件，跳过隐藏文件、子目录与 `*.test.ts`。

### 测试

```bash
uv run --no-project --with pytest pytest tests
```

`tests/test_omp_loading.py` 在临时 HOME 中运行本机 `omp`，对接一个假的 CPA，分别验证两种加载方式：复制到 `~/.omp/agent/extensions/` 下的包目录，以及 `omp plugin install` 安装整个仓库（默认安装本地工作树）。推送后可验证 Git 安装：

```bash
OMP_EXTENSIONS_PLUGIN_SOURCE=github:233Official/omp-extensions#main \
  uv run --no-project --with pytest pytest tests/test_omp_loading.py
```

### 本机同步

`scripts/sync_omp_extension.py` 把一个扩展目录单向复制到 OMP 扩展目录，由用户级 LaunchAgent 在后台每 2 秒检查一次，内容稳定后整包替换。部署副本不引用源路径，仓库所在磁盘未挂载时 OMP 仍加载最后一次同步的版本。每个扩展一个实例，实例名通常取扩展目录名。

需用系统盘上的 Python 3.10+ 运行安装命令；在仓库根目录执行：

```bash
python3 scripts/sync_omp_extension.py --instance openai-codex-endpoint install \
  --source "$PWD/openai-codex-endpoint" \
  --target "$HOME/.omp/agent/extensions/openai-codex-endpoint" \
  --git-commit
python3 scripts/sync_omp_extension.py --instance openai-codex-endpoint sync
python3 scripts/sync_omp_extension.py --instance openai-codex-endpoint start
python3 scripts/sync_omp_extension.py --instance openai-codex-endpoint status
```

| 动作 | 行为 |
| --- | --- |
| `install` | 安装或更新运行副本与 LaunchAgent，不启动、不复制；首次安装时目标须不存在或与源一致；同一实例不能改绑源或目标 |
| `sync` | 立即同步；未完成或有冲突时退出码为 2 |
| `sync --overwrite-target` | 先备份目标，再用稳定的源覆盖，用于处理冲突 |
| `start` / `stop` | 启用或停用后台同步，保留部署文件 |
| `status` | 显示同步状态、冲突标记与两端是否一致 |
| `uninstall` | 停止并删除 LaunchAgent 与运行脚本，保留目标、配置、状态和备份 |

- 运行目录：`~/Library/Application Support/omp-extensions/sync/<实例>/`（配置、状态、冲突备份、运行脚本）。
- LaunchAgent：`~/Library/LaunchAgents/io.github.233official.omp-extensions.sync.<实例>.plist`。
- `--git-commit`：目标位于 Git 仓库（如 `~/.omp` 配置仓库）时，扩展 `package.json` 的 `version` 变化的那次同步只提交目标目录，提交信息为 `config🔧: <目录名> update <旧版本> -> <新版本>`，首次部署为 `config🔧: <目录名> install <版本>`；其他已暂存内容不进入该提交，不推送。版本号不变的同步只更新文件。
- 目标被单独修改、增删文件或删除时锁定为冲突，进程重启后仍保持，需检查后执行 `sync --overwrite-target`。不要直接编辑部署副本。
- 源缺失、磁盘未挂载、缺少 `package.json` 时保留现有部署，源恢复后自动继续。
- 同步只做文件复制，不做类型检查或功能验证；修改后新开 OMP 进程验收。
- 更新同步工具本身：`stop`，再用相同参数重新 `install`，然后 `start`。
- 新增扩展：用新的实例名执行同样的 `install`、`sync`、`start`；若目标仓库默认忽略扩展目录（如 `~/.omp` 配置仓库），先在其 `.gitignore` 放行新目录，否则自动提交记为 `commit_target_ignored`。

## 许可

[MIT](LICENSE)
