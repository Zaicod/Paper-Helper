import { useEffect, useState } from "react";
import { Check, Crown, Gauge, KeyRound, LoaderCircle, RotateCcw, Save, ShieldCheck, SlidersHorizontal, WalletCards } from "lucide-react";
import { applyModelPreset, getModelSettings, removeProviderOverride, saveAgentModel, saveProvider } from "../api";
import { PanelHeader } from "../components/ui";
import type { AgentModelSetting, ProviderSetting, User, UserModelSettings } from "../types";

const presetCopy = {
  economy: { title: "额度优先", text: "全部使用 Flash，适合逐篇批量分析。", icon: WalletCards },
  balanced: { title: "均衡推荐", text: "分析和导图用 Flash，总结用 Plus，创新用 Max。", icon: Gauge },
  quality: { title: "质量优先", text: "全部使用 Max，适合少量论文的最终报告。", icon: Crown },
};

export function SettingsPage({ user, onError }: { user: User; onError: (message: string | null) => void }) {
  const [settings, setSettings] = useState<UserModelSettings | null>(null);
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState<string | null>(null); const [saved, setSaved] = useState<string | null>(null);
  const [providerDrafts, setProviderDrafts] = useState<Record<string, { api_key: string; base_url: string }>>({});
  const [agentDrafts, setAgentDrafts] = useState<Record<string, { provider: string; model_name: string }>>({});

  async function load() {
    setLoading(true);
    try {
      const value = await getModelSettings(); setSettings(value);
      setProviderDrafts(Object.fromEntries(value.providers.map((provider) => [provider.provider, { api_key: "", base_url: provider.base_url }])));
      setAgentDrafts(Object.fromEntries(value.agents.map((agent) => [agent.agent_role, { provider: agent.provider, model_name: agent.model_name }])));
    } catch (caught) { onError(caught instanceof Error ? caught.message : "模型设置加载失败"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  function markSaved(key: string) { setSaved(key); window.setTimeout(() => setSaved((current) => current === key ? null : current), 1800); }

  async function saveProviderCard(provider: ProviderSetting) {
    const draft = providerDrafts[provider.provider]; setBusy(`provider-${provider.provider}`); onError(null);
    try { await saveProvider(provider.provider, draft); markSaved(`provider-${provider.provider}`); await load(); }
    catch (caught) { onError(caught instanceof Error ? caught.message : "Provider 保存失败"); }
    finally { setBusy(null); }
  }
  async function resetProvider(provider: ProviderSetting) {
    if (!window.confirm(`移除 ${provider.label} 的个人密钥，并恢复环境变量配置？`)) return;
    setBusy(`provider-${provider.provider}`);
    try { await removeProviderOverride(provider.provider); await load(); }
    catch (caught) { onError(caught instanceof Error ? caught.message : "个人密钥移除失败"); }
    finally { setBusy(null); }
  }
  async function saveAgent(agent: AgentModelSetting) {
    const draft = agentDrafts[agent.agent_role]; setBusy(`agent-${agent.agent_role}`); onError(null);
    try { await saveAgentModel(agent.agent_role, draft); markSaved(`agent-${agent.agent_role}`); await load(); }
    catch (caught) { onError(caught instanceof Error ? caught.message : "Agent 模型保存失败"); }
    finally { setBusy(null); }
  }
  async function applyPreset(name: string) {
    setBusy(`preset-${name}`); onError(null);
    try { await applyModelPreset(name); await load(); markSaved(`preset-${name}`); }
    catch (caught) { onError(caught instanceof Error ? caught.message : "推荐方案应用失败"); }
    finally { setBusy(null); }
  }

  if (loading && !settings) return <section className="panel settings-loading"><LoaderCircle className="spin" />读取个人模型路由…</section>;
  if (!settings) return null;
  return <div className="settings-page">
    <section className="settings-hero"><div><span>PERSONAL MODEL ROUTER</span><h2>{user.username} 的 Agent 控制台</h2><p>为不同职责选择合适的模型。配置只属于当前账号，API Key 加密保存且不会再次显示明文。</p></div><div className="security-pill"><ShieldCheck size={22} /><div><strong>密钥已保护</strong><small>Fernet 加密 · API 仅返回掩码</small></div></div></section>

    <section className="panel settings-section"><PanelHeader icon={Gauge} title="推荐搭配" subtitle="先套用方案，再按 Agent 单独微调" /><div className="preset-grid">{Object.entries(presetCopy).map(([name, copy]) => { const Icon = copy.icon; return <article key={name}><Icon size={20} /><div><strong>{copy.title}</strong><p>{copy.text}</p></div><button onClick={() => void applyPreset(name)} disabled={busy === `preset-${name}`}>{busy === `preset-${name}` ? <LoaderCircle className="spin" size={15} /> : saved === `preset-${name}` ? <Check size={15} /> : "应用"}</button></article>; })}</div><p className="settings-hint">推荐是起点，不是绝对答案。应使用同一批论文做质量、延迟和 token 消耗对比，再保留满足质量要求的最轻模型。</p></section>

    <section className="panel settings-section"><PanelHeader icon={KeyRound} title="Provider 与密钥" subtitle="个人配置优先于服务器环境变量" /><div className="provider-grid">{settings.providers.map((provider) => {
      const draft = providerDrafts[provider.provider]; const key = `provider-${provider.provider}`;
      const placeholder = provider.credential_source === "personal" ? "留空表示不替换个人密钥" : provider.credential_source === "environment" ? "填写后创建个人覆盖" : "输入 API Key";
      return <article className="provider-card" key={provider.provider}><header><div><strong>{provider.label}</strong><span className={`credential-state ${provider.credential_source}`}>{provider.credential_source === "personal" ? "个人密钥" : provider.credential_source === "environment" ? "环境变量" : "未配置"}</span></div>{provider.api_key_hint && <small>{provider.api_key_hint}</small>}</header><label>Base URL<input value={draft?.base_url ?? ""} onChange={(event) => setProviderDrafts((current) => ({ ...current, [provider.provider]: { ...current[provider.provider], base_url: event.target.value } }))} /></label><label>API Key<input type="password" autoComplete="new-password" value={draft?.api_key ?? ""} onChange={(event) => setProviderDrafts((current) => ({ ...current, [provider.provider]: { ...current[provider.provider], api_key: event.target.value } }))} placeholder={placeholder} /></label><div className="provider-actions">{provider.credential_source === "personal" && <button className="ghost-button" onClick={() => void resetProvider(provider)}><RotateCcw size={14} />恢复环境配置</button>}<button onClick={() => void saveProviderCard(provider)} disabled={busy === key}>{busy === key ? <LoaderCircle className="spin" size={15} /> : saved === key ? <Check size={15} /> : <Save size={15} />}保存</button></div></article>;
    })}</div></section>

    <section className="panel settings-section"><PanelHeader icon={SlidersHorizontal} title="Agent 独立模型" subtitle="分析、总结、创新和导图互不绑定" /><div className="agent-routing-grid">{settings.agents.map((agent) => { const draft = agentDrafts[agent.agent_role]; const provider = settings.providers.find((item) => item.provider === draft?.provider); const key = `agent-${agent.agent_role}`; return <article key={agent.agent_role}><div className="agent-role"><span>{agent.agent_role.toUpperCase()}</span><strong>{agent.label}</strong></div><label>Provider<select value={draft?.provider ?? "qwen"} onChange={(event) => { const nextProvider = settings.providers.find((item) => item.provider === event.target.value); setAgentDrafts((current) => ({ ...current, [agent.agent_role]: { provider: event.target.value, model_name: nextProvider?.models[0] ?? "" } })); }}>{settings.providers.map((item) => <option value={item.provider} key={item.provider}>{item.label}{item.has_api_key ? "" : " · 未配置 Key"}</option>)}</select></label><label>模型 ID<input list={`models-${agent.agent_role}`} value={draft?.model_name ?? ""} onChange={(event) => setAgentDrafts((current) => ({ ...current, [agent.agent_role]: { ...current[agent.agent_role], model_name: event.target.value } }))} /><datalist id={`models-${agent.agent_role}`}>{provider?.models.map((model) => <option value={model} key={model} />)}</datalist></label><button onClick={() => void saveAgent(agent)} disabled={busy === key}>{busy === key ? <LoaderCircle className="spin" size={15} /> : saved === key ? <Check size={15} /> : <Save size={15} />}保存此 Agent</button></article>; })}</div></section>
  </div>;
}
