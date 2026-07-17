/** 主流 AI 服务商预设模板 */

export interface AgentPreset {
  name: string;
  description: string;
  category: 'cloud' | 'local' | 'other';
  method: string;
  auth_type: string;
  api_base_url: string;
  headers_template?: string;
  body_template: string;
  /** 提示：该预设对应的请求体结构说明 */
  hint?: string;
}

export interface JudgePreset {
  name: string;
  description: string;
  category: 'cloud' | 'local' | 'other';
  provider: string;
  api_base_url: string;
  auth_type: string;
}

/** Agent 预设 - 智能体配置 */
export const AGENT_PRESETS: AgentPreset[] = [
  // ── 互联网在线服务 ──
  {
    name: 'OpenAI GPT / DeepSeek',
    description: 'OpenAI 兼容的聊天补全接口，适用于 GPT-4o、DeepSeek、通义千问等',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://api.deepseek.com/chat/completions',
    body_template: JSON.stringify({
      model: 'deepseek-chat',
      messages: [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: '{{input}}' },
      ],
      temperature: 0.7,
      max_tokens: 2048,
    }, null, 2),
    hint: '支持 {{input}} 占位符，运行时自动替换为测试用例的输入',
  },
  {
    name: 'Anthropic Claude',
    description: 'Anthropic Messages API',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://api.anthropic.com/v1/messages',
    body_template: JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 1024,
      messages: [
        { role: 'user', content: '{{input}}' },
      ],
    }, null, 2),
    hint: 'Anthropic API 使用 x-api-key 认证，请确保认证方式选择 bearer',
  },
  {
    name: '通义千问 (Qwen)',
    description: '阿里云通义千问兼容 OpenAI 接口',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
    body_template: JSON.stringify({
      model: 'qwen-plus',
      messages: [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: '{{input}}' },
      ],
    }, null, 2),
  },
  {
    name: '智谱 GLM',
    description: '智谱开放平台 API',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
    body_template: JSON.stringify({
      model: 'glm-4-plus',
      messages: [
        { role: 'user', content: '{{input}}' },
      ],
    }, null, 2),
  },
  {
    name: '月之暗面 Moonshot',
    description: 'Moonshot AI 开放平台',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://api.moonshot.cn/v1/chat/completions',
    body_template: JSON.stringify({
      model: 'moonshot-v1-8k',
      messages: [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: '{{input}}' },
      ],
    }, null, 2),
  },
  {
    name: '百度千帆',
    description: '百度智能云千帆大模型平台',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions',
    body_template: JSON.stringify({
      messages: [
        { role: 'user', content: '{{input}}' },
      ],
    }, null, 2),
  },
  {
    name: 'Dify 对话型应用',
    description: 'Dify Chatflow / Agent 应用的消息接口',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://dify.example.com/v1/chat-messages',
    body_template: JSON.stringify({
      inputs: {},
      query: '{{input}}',
      response_mode: 'blocking',
      conversation_id: '',
      user: 'test-user',
    }, null, 2),
  },
  {
    name: 'Google Gemini',
    description: 'Google Gemini API (兼容 OpenAI 格式需额外配置)',
    category: 'cloud',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent',
    body_template: JSON.stringify({
      contents: [
        {
          parts: [
            { text: '{{input}}' },
          ],
        },
      ],
    }, null, 2),
  },

  // ── 本地/私有化部署 ──
  {
    name: 'Ollama (本机)',
    description: '本机部署的 Ollama，兼容 OpenAI 接口',
    category: 'local',
    method: 'POST',
    auth_type: 'none',
    api_base_url: 'http://localhost:11434/v1/chat/completions',
    body_template: JSON.stringify({
      model: 'llama3.2',
      messages: [
        { role: 'user', content: '{{input}}' },
      ],
      stream: false,
    }, null, 2),
  },
  {
    name: 'vLLM (私有化)',
    description: '企业本地 vLLM 推理服务',
    category: 'local',
    method: 'POST',
    auth_type: 'none',
    api_base_url: 'http://internal-api:8000/v1/chat/completions',
    body_template: JSON.stringify({
      model: 'Qwen2.5-7B-Instruct',
      messages: [
        { role: 'user', content: '{{input}}' },
      ],
      temperature: 0.7,
      max_tokens: 2048,
    }, null, 2),
  },
  {
    name: '自定义 JSON 回显',
    description: '发送简单 JSON 结构，用于调试连通性',
    category: 'other',
    method: 'POST',
    auth_type: 'none',
    api_base_url: 'http://localhost:8080/echo',
    body_template: JSON.stringify({
      input: '{{input}}',
      timestamp: '{{$TIMESTAMP}}',
    }, null, 2),
  },
];

/** Judge 预设 - AI 评估模型 */
export const JUDGE_PRESETS: JudgePreset[] = [
  { name: 'OpenAI GPT-4o', provider: 'openai', api_base_url: 'https://api.openai.com/v1', auth_type: 'bearer', description: '互联网在线模型', category: 'cloud' },
  { name: 'DeepSeek', provider: 'custom', api_base_url: 'https://api.deepseek.com/v1', auth_type: 'bearer', description: '互联网在线模型', category: 'cloud' },
  { name: 'Anthropic Claude', provider: 'anthropic', api_base_url: 'https://api.anthropic.com', auth_type: 'bearer', description: '互联网在线模型', category: 'cloud' },
  { name: '通义千问', provider: 'custom', api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', auth_type: 'bearer', description: '互联网在线模型', category: 'cloud' },
  { name: '智谱 GLM', provider: 'custom', api_base_url: 'https://open.bigmodel.cn/api/paas/v4', auth_type: 'bearer', description: '互联网在线模型', category: 'cloud' },
  { name: 'Ollama (本机)', provider: 'custom', api_base_url: 'http://localhost:11434/v1', auth_type: 'none', description: '本机部署模型', category: 'local' },
  { name: 'vLLM (企业)', provider: 'custom', api_base_url: 'http://internal-api:8000/v1', auth_type: 'none', description: '企业本地服务', category: 'local' },
];
