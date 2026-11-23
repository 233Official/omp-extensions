import * as fs from "node:fs";
import * as path from "node:path";
import { fetchCodexModels } from "@oh-my-pi/pi-catalog/discovery/codex";
import { isOfficialCodexApiUrl } from "@oh-my-pi/pi-catalog/wire/codex";
import { getAgentDir } from "@oh-my-pi/pi-coding-agent";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent/extensibility/extensions";

const PROVIDER = "openai-codex";
const INFERENCE_SUFFIX = "/backend-api";
const CPA_MODELS_PATH = "/v1/models";

/**
 * 让 openai-codex 在 CPA 上同时完成地址切换和模型发现，保留 OMP 对该 provider 的内置策略。
 *
 * - 地址：CODEX_CPA_BASE_URL 非空时覆盖运行时地址，供启动脚本在多个 CPA 之间切换；
 *   否则沿用 models.yml 中 openai-codex 的 baseUrl。只改运行时注册，不写回配置，不碰认证。
 * - 发现：OMP 原生 Codex 发现只请求 {baseUrl}/codex/models 与 {baseUrl}/models，CPA 不提供这两个路由；
 *   CPA 在 {根地址}/v1/models?client_version=... 返回同格式的 Codex 目录。这里复用 OMP 自带的
 *   Codex 目录解析，只注册 gpt- 开头的可见模型，推理仍走同一 CPA 的 /backend-api。
 * - 官方 chatgpt.com 端点或未配置地址时不启用本扩展，保持 OMP 原生行为；地址不以 /backend-api 结尾时
 *   记录警告后跳过，不阻断 OMP 启动。
 */
export default (pi: ExtensionAPI) => {
	const overrideBaseUrl = process.env.CODEX_CPA_BASE_URL?.trim() || undefined;
	const baseUrl = overrideBaseUrl ?? readConfiguredBaseUrl();
	if (!baseUrl || isOfficialCodexApiUrl(baseUrl)) return;

	const cpaRoot = cpaRootOf(baseUrl);
	if (!cpaRoot) {
		pi.logger.warn(`openai-codex-endpoint: disabled, baseUrl ${baseUrl} does not end with ${INFERENCE_SUFFIX}`);
		return;
	}

	pi.registerProvider(PROVIDER, {
		baseUrl,
		discoverModels: ({ accounts, fetch }) => {
			// CPA 只使用配置的 API key，不把已登录的 Codex OAuth 凭据发给中转。
			const key = accounts.find(account => !("ok" in account) && !account.accountId)?.apiKey;
			return fetchCpaCodexModels(cpaRoot, baseUrl, key, fetch);
		},
	});

	if (!overrideBaseUrl) return;
	// 当前模型可能在覆盖前已选定，须重新绑定才能让首个请求使用新地址。
	pi.on("session_start", async (_event, ctx) => {
		const current = ctx.model;
		if (current?.provider !== PROVIDER) return;
		const updated = ctx.modelRegistry.find(current.provider, current.id);
		if (!updated) throw new Error(`openai-codex-endpoint: current model ${current.id} not found after endpoint override`);
		await pi.setModel(updated);
	});
};

/** models.yml（或 models.yaml）中 openai-codex 的 baseUrl；未配置时返回 undefined。 */
function readConfiguredBaseUrl(): string | undefined {
	for (const name of ["models.yml", "models.yaml"]) {
		const file = path.join(getAgentDir(), name);
		if (!fs.existsSync(file)) continue;
		const config = Bun.YAML.parse(fs.readFileSync(file, "utf8")) as {
			providers?: Record<string, { baseUrl?: unknown } | undefined>;
		} | null;
		const value = config?.providers?.[PROVIDER]?.baseUrl;
		return typeof value === "string" && value.trim() ? value.trim() : undefined;
	}
	return undefined;
}

/** https://host/backend-api → https://host；不以 /backend-api 结尾时返回 undefined。 */
function cpaRootOf(baseUrl: string): string | undefined {
	const normalized = baseUrl.replace(/\/+$/, "");
	return normalized.endsWith(INFERENCE_SUFFIX) ? normalized.slice(0, -INFERENCE_SUFFIX.length) : undefined;
}

/**
 * 失败一律抛错而不是返回空数组：OMP 把成功结果视为权威目录，空数组会清空 openai-codex 的模型列表，
 * 抛错则保留上次缓存。
 *
 * 保留 OMP 解析出的完整 ModelSpec（包括 serviceTiers），只替换推理地址。
 */
async function fetchCpaCodexModels(
	cpaRoot: string,
	baseUrl: string,
	apiKey: string | undefined,
	fetchFn: NonNullable<Parameters<typeof fetchCodexModels>[0]["fetchFn"]>,
) {
	if (!apiKey) throw new Error("openai-codex-endpoint: no openai-codex API key for CPA model discovery");
	const result = await fetchCodexModels({ accessToken: apiKey, baseUrl: cpaRoot, paths: [CPA_MODELS_PATH], fetchFn });
	if (!result) throw new Error(`openai-codex-endpoint: ${cpaRoot}${CPA_MODELS_PATH} returned no Codex model catalog`);
	if (result.rejectedStatus) {
		throw new Error(`openai-codex-endpoint: ${cpaRoot}${CPA_MODELS_PATH} rejected the key (HTTP ${result.rejectedStatus})`);
	}
	const models = result.models.filter(model => model.id.startsWith("gpt-"));
	if (models.length === 0) {
		throw new Error(`openai-codex-endpoint: ${cpaRoot}${CPA_MODELS_PATH} listed no visible gpt- models`);
	}
	return models.map(model => ({ ...model, baseUrl }));
}
