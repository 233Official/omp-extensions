"""在隔离 HOME 中用真实 omp 加载扩展，覆盖两种加载方式：

- ``extensions``：同步脚本部署的方式，包目录位于 ``~/.omp/agent/extensions/<名称>/``；
- ``plugin``：朋友使用的方式，``omp plugin install`` 安装整个仓库。默认安装本地工作树（OMP 对本地路径执行 link）；
  设置 ``OMP_EXTENSIONS_PLUGIN_SOURCE``（如 ``github:233Official/omp-extensions#main``）时改为从该来源安装，
  用于推送后验证朋友实际的 Git 安装。

本机模型服务只是一个假的 CPA，不需要真实凭据；只有指定 Git 来源时才访问网络。
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest

REPO = Path(__file__).resolve().parents[1]
EXTENSION = REPO / "openai-codex-endpoint"
KEY = "test-cpa-key"
KEY_VARIABLE = "OMP_TEST_CPA_KEY"

CATALOG = {
    "models": [
        {
            "slug": "gpt-test-cpa",
            "display_name": "GPT Test CPA",
            "visibility": "list",
            "context_window": 400000,
            "max_context_window": 400000,
            "input_modalities": ["text", "image"],
            "default_reasoning_level": "medium",
            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}],
            "priority": 1,
        },
        {"slug": "gpt-test-hidden", "display_name": "Hidden", "visibility": "hide", "priority": 2},
        {"slug": "deepseek-test", "display_name": "Not OpenAI", "visibility": "list", "priority": 3},
    ]
}

pytestmark = pytest.mark.skipif(shutil.which("omp") is None, reason="omp 不在 PATH")


class FakeCpa(BaseHTTPRequestHandler):
    requests: list[tuple[str, str | None]] = []

    def do_GET(self) -> None:  # noqa: N802
        FakeCpa.requests.append((self.path, self.headers.get("Authorization")))
        if self.path.split("?", 1)[0] != "/v1/models":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            self.send_error(401)
            return
        body = json.dumps(CATALOG).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


@pytest.fixture
def cpa():
    FakeCpa.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeCpa)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def isolated_home(tmp_path: Path, base_url: str) -> Path:
    home = tmp_path / "home"
    agent = home / ".omp/agent"
    agent.mkdir(parents=True)
    (agent / "config.yml").write_text("{}\n")
    (agent / "models.yml").write_text(
        "providers:\n"
        "  openai-codex:\n"
        f"    baseUrl: {base_url}\n"
        "    auth: apiKey\n"
        f"    apiKey: {KEY_VARIABLE}\n"
    )
    return home


def omp(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
        KEY_VARIABLE: KEY,
    }
    return subprocess.run(["omp", *args], cwd=home, env=env, capture_output=True, text=True, timeout=180)


def deploy_extension_dir(home: Path) -> None:
    target = home / ".omp/agent/extensions" / EXTENSION.name
    target.mkdir(parents=True)
    for path in EXTENSION.iterdir():
        if path.is_file() and not path.name.startswith(".") and not path.name.endswith(".test.ts"):
            shutil.copy2(path, target / path.name)


def install_plugin(home: Path) -> None:
    source = os.environ.get("OMP_EXTENSIONS_PLUGIN_SOURCE") or str(REPO)
    result = omp(home, "plugin", "install", source)
    assert result.returncode == 0, result.stdout + result.stderr


def listed_models(home: Path) -> dict[str, dict]:
    refresh = omp(home, "models", "refresh")
    assert refresh.returncode == 0, refresh.stdout + refresh.stderr
    result = omp(home, "models", "openai-codex", "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    rows = payload["models"] if isinstance(payload, dict) else payload
    return {row["id"]: row for row in rows if row.get("provider") == "openai-codex"}


@pytest.mark.parametrize("mode", ["extensions", "plugin"])
def test_cpa_models_are_discovered_under_openai_codex(tmp_path, cpa, mode):
    home = isolated_home(tmp_path, f"{cpa}/backend-api")
    if mode == "extensions":
        deploy_extension_dir(home)
    else:
        install_plugin(home)

    models = listed_models(home)

    assert "gpt-test-cpa" in models
    assert "gpt-test-hidden" not in models
    assert "deepseek-test" not in models
    assert any(path.startswith("/v1/models?client_version=") and auth == f"Bearer {KEY}"
               for path, auth in FakeCpa.requests)


@pytest.mark.parametrize("mode", ["extensions", "plugin"])
def test_non_cpa_base_url_disables_extension_without_breaking_omp(tmp_path, cpa, mode):
    # 不以 /backend-api 结尾的地址：扩展应跳过；OMP 原生 Codex 发现只会请求 /proxy/codex/models 与 /proxy/models。
    home = isolated_home(tmp_path, f"{cpa}/proxy")
    if mode == "extensions":
        deploy_extension_dir(home)
    else:
        install_plugin(home)

    models = listed_models(home)

    assert "gpt-test-cpa" not in models
    assert not any(path.startswith("/v1/models") for path, _ in FakeCpa.requests)
