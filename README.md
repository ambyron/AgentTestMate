<div align="center">
  <br>
  <h1>AgentTestMate</h1>
  <p><strong>AI Agent 评测平台 — 智能体性能评估助手</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python">
    <img src="https://img.shields.io/badge/React-18-blue" alt="React">
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688" alt="FastAPI">
    <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License">
    <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs">
  </p>

  <br>
</div>

---
## 使用提示
此项目为开源项目, 用于个人研究学习, 适用Apache License 2.0协议, 欢迎使用并参与产品共创。 您可以通过 Issues 提交您对项目的建议/需求/Bug,  也欢迎贡献新的功能代码。

## 📖 简介

AgentTestMate 是一个面向 AI 智能体（Agent）的全流程评测工具。它提供从测试数据集管理、评测规则配置、AI 评估模型接入到任务执行和结果分析的一站式解决方案，帮助开发者和团队系统性地评估 AI Agent 的性能表现。


无论是 OpenAI / Anthropic 等商业模型，还是本地部署的开源模型，AgentTestMate 都能作为统一的评测基准平台，支持多维度、多策略的自动化评分。

---

## ✨ 功能特性

- **🤖 智能体管理** — 管理待评测的 AI Agent 配置（API 地址、认证方式、请求模板），支持 OpenAI、DeepSeek、Dify、通义千问等预设模板
- **📊 数据集管理** — 创建和管理测试用例，支持 JSON / CSV / YAML / XLSX 批量导入，自动解析测试数据
- **📐 评估规则** — 灵活配置评分规则：精确匹配、关键词匹配、正则表达式、响应时长、输出长度等
- **🧠 AI 评估模型** — 接入 LLM 作为评分裁判，支持 OpenAI / Anthropic / 自定义 API 兼容接口
- **🎯 多策略评分** — 通用评分、参照对比、多维度评分（Rubric）、思维链推理、少样本示例、对比选择
- **⚡ 并发执行** — 支持高并发任务执行，带暂停 / 恢复 / 取消控制
- **📋 任务管理** — 评测任务的创建、执行、进度追踪、结果查看
- **📈 结果分析** — 详细评分明细、通过率统计、多任务对比
- **🧾 报告导出** — 支持 HTML / CSV / Markdown / JSON 格式导出
- **✅ 人工审核** — 对评测结果进行人工标注和审核，持续提升评估准确度
- **🔒 数据隔离** — 多用户空间隔离，保障数据安全

---

## 🧩 功能详解

### 🤖 智能体管理

智能体是接受评测的目标系统。AgentTestMate 将每个待评测的 AI Agent 封装为一个统一的配置单元：

**核心配置：**

| 配置项         | 说明                                            | 示例                                                       |
| -------------- | ----------------------------------------------- | ---------------------------------------------------------- |
| **API 地址**   | Agent 服务端点的 URL                            | `https://api.deepseek.com/chat/completions`                |
| **请求方法**   | HTTP 请求方法                                   | `POST` / `GET`                                             |
| **认证方式**   | 支持的认证类型                                  | `Bearer Token` / `API Key` / `Basic Auth` / `无认证`       |
| **请求模板**   | 定义请求体的 JSON 结构，支持 `{{input}}` 占位符 | `{"messages": [{"role": "user", "content": "{{input}}"}]}` |
| **响应头模板** | 自定义 HTTP 头                                  | `{"X-Custom-Header": "value"}`                             |

**内置预设：**
AgentTestMate 提供了多种主流 AI 服务的预设配置，选择即用：

- OpenAI / DeepSeek 聊天补全接口
- Dify 对话型应用接口
- 通义千问（Qwen）兼容接口
- 支持自定义接入任意 HTTP API 接口

---

### 📊 数据集管理

数据集是评测的基础素材，由一组测试用例（Test Case）组成。每个测试用例包含：

**用例结构：**

```json
{
  "case_id": "TC-001",
  "input": "请解释什么是量子计算",
  "expected_output": "量子计算是一种利用量子力学原理进行计算的技术...",
  "objectives": ["准确性", "完整性"],
  "tags": ["科普", "技术"],
  "rule_refs": []
}
```

| 字段              | 说明                                     |
| ----------------- | ---------------------------------------- |
| `case_id`         | 用例唯一标识，用于结果追踪               |
| `input`           | 发送给智能体的输入提示词                 |
| `expected_output` | 期望的理想输出，用于参照对比评分         |
| `objectives`      | 该用例需要评估的维度标签                 |
| `tags`            | 分类标签，可用于任务过滤筛选             |
| `rule_refs`       | 指定仅使用哪些规则评估（留空则使用全部） |

**数据导入：**

- 支持 JSON / CSV / YAML / XLSX 四种格式
- 自动解析 CSV 中的 JSON 数组字段（objectives、tags 等）
- 导入时自动清理 NaN 值、转换 NumPy 类型为标准 Python 类型
- 文件大小限制 5MB

---

### 📐 评估规则

评估规则是评分系统的核心。AgentTestMate 支持多种规则类型，可以组合使用：

| 规则类型       | 原理                         | 适用场景                                 |
| -------------- | ---------------------------- | ---------------------------------------- |
| **精确匹配**   | 实际输出与期望输出完全相同   | 答案确定的场景（选择题、数字输出）       |
| **关键词匹配** | 检查输出中是否包含指定关键词 | 内容覆盖率检查，自动从期望输出提取关键词 |
| **正则表达式** | 用正则模式匹配输出内容       | 格式验证（邮箱、电话号码、代码结构）     |
| **响应时长**   | 检查响应时间是否在允许范围内 | 性能基准测试、SLA 验证                   |
| **输出长度**   | 检查输出字符数是否在范围内   | Token 消耗控制、简洁性验证               |
| **LLM 评分**   | 使用 AI 模型作为裁判评分     | 开放性问题、需要语义理解的场景           |

**规则配置参数：**

- **权重（Weight）** — 每条规则在总分中的权重
- **阈值（Threshold）** — 通过/失败的判定分数线
- **启/禁用** — 灵活控制规则是否参与评分
- **关联维度** — 规则可绑定到评估维度，实现分维度评分

---

### 🧠 AI 评估模型

AI 评估模型（Judge Model）是作为评分裁判的 LLM。AgentTestMate 支持多模型接入：

**支持的 Provider：**

| Provider  | API 格式               | 默认模型                   |
| --------- | ---------------------- | -------------------------- |
| OpenAI    | `/v1/chat/completions` | `gpt-4o`                   |
| Anthropic | `/v1/messages`         | `claude-sonnet-4-20250514` |
| Google    | 兼容 OpenAI 格式       | `gemini-pro`               |
| Azure     | 兼容 OpenAI 格式       | `gpt-4o`                   |
| 自定义    | 兼容 OpenAI 格式       | 任意模型名                 |

**凭据安全：**

- API Key 使用 AES-256-GCM 算法加密后存储于数据库
- 日志自动脱敏，仅显示前 10 个字符
- 支持连通性检测，验证模型服务可用性

**多裁判仲裁：**

- 支持一个评测任务使用多个 Judge Model 并行评分
- 内置仲裁策略：平均值、最小值、最大值、加权平均
- 自动检测高方差（judge 间分歧大时告警）

---

### 🎯 评分策略

对于 AI 评分类规则（LLM Judge），AgentTestMate 提供 6 种评测策略：

| 策略                           | 说明                           | 最佳实践             |
| ------------------------------ | ------------------------------ | -------------------- |
| **Simple（通用评分）**         | AI 根据输入和输出直接评分      | 一般性问答评测       |
| **Reference（参照对比）**      | 对比实际输出与期望输出的匹配度 | 有明确预期答案的任务 |
| **Rubric（多维度评分）**       | 按评分维度逐一打分再加权汇总   | 复杂任务的多维度评估 |
| **Chain-of-Thought（思维链）** | 先逐步推理分析，再给出最终评分 | 需要深入推理的评测   |
| **Few-Shot（少样本）**         | 参考若干评分示例后给出评分     | 需要校准评分标准     |
| **Pairwise（对比选择）**       | 比较两个输出的优劣并打分       | A/B 测试、模型对比   |

每种策略都有内置的默认提示词模板（支持中英文），也可以自定义模板内容。

**评分流程：**

```
规则配置 → 选择策略 → 选择Judge Model
                        ↓
   评分结果 ← 解析响应 ← LLM 调用 ← 渲染提示词模板
```

---

### ⚡ 任务执行引擎

评测任务是整个评估流程的执行单元。任务引擎负责调度和执行：

**执行流程：**

1. **加载配置** — 读取任务关联的智能体、数据集、规则
2. **预加载资源** — 加载 AI Judge 模型、提示词模板、评分规约
3. **并发执行** — 使用 Semaphore 控制并发度，逐个执行测试用例
4. **实时评分** — 每执行完一个用例立即调用评分规则计算得分
5. **进度追踪** — 支持 SSE 实时推送进度，前端展示进度条
6. **结果持久化** — 评分完成后写入数据库

**生命周期控制：**

| 操作     | 效果                               |
| -------- | ---------------------------------- |
| **创建** | 配置任务参数，设定为 pending 状态  |
| **开始** | 启动后台执行线程，状态变为 running |
| **暂停** | 暂停任务执行（已执行的用例保留）   |
| **恢复** | 继续执行暂停的任务                 |
| **取消** | 取消剩余未执行的用例               |
| **重跑** | 复制任务配置，创建新的任务重新执行 |

**容错机制：**

- 指数退避重试（Retry with Exponential Backoff）
- 可重试的错误类型：超时、连接错误、5xx、429（限流）
- 单个 Agent 调用失败不影响其他用例执行

---

### 📈 结果分析

执行完成后，系统提供多维度、多层级的结果分析：

**概览统计：**

- 总用例数、通过数、失败数
- 通过率（百分比）
- 平均评分

**逐条详情：**

- 每个用例的输入、输出、预期输出
- 每条规则的评分明细（得分 + PASS/FAIL）
- 每个评估维度的得分和通过状态

**评分聚合逻辑：**

```
单条规则评分 → 按规则权重加权 → 分维度聚合
                                    ↓
                        全局通过判断 ← 全局通过线 (Global Threshold)
```

**多任务对比：**

- 支持选择多个已完成任务进行对比
- 并列展示各任务的 summary 统计

---

### 🧾 报告导出

支持 4 种格式的完整报告导出：

| 格式         | 特点                      | 包含内容                     |
| ------------ | ------------------------- | ---------------------------- |
| **JSON**     | 结构化数据，适合程序处理  | 完整结果 + 元信息 + 审核数据 |
| **CSV**      | 表格格式，适合 Excel 打开 | 每条用例含评分/审核列        |
| **Markdown** | 可读性好，适合嵌入文档    | 汇总表 + 明细表              |
| **HTML**     | 美观大屏，适合分享        | 样式卡片 + 内嵌子表格        |

所有格式包含：任务元信息（智能体、数据集、规则、AI 模型）、每条用例的最新审核记录。

---

### ✅ 人工审核

自动评分之外，AgentTestMate 支持人工对评测结果进行审核：

| 审核字段         | 说明                                                            |
| ---------------- | --------------------------------------------------------------- |
| **评分（1-10）** | 人工给出的审核评分                                              |
| **标签**         | `正确 (correct)` / `错误 (incorrect)` / `需复查 (needs_review)` |
| **评语**         | 对评测结果的人工意见                                            |

审核数据会在评测详情页中按用例展示（显示最新一条审核记录），并可用于后续的 AI Judge 准确度分析。

---

### 🔒 数据隔离

AgentTestMate 使用工作空间（Space）机制实现多用户数据隔离：

| 机制           | 说明                                              |
| -------------- | ------------------------------------------------- |
| **空间隔离**   | 每个用户拥有独立的工作空间，数据互不可见          |
| **管理员模式** | Admin 用户拥有全局访问权限（不受空间限制）        |
| **默认空间**   | 首次启动自动创建 Default Space，兼容单用户模式    |
| **数据归属**   | 所有资源创建时自动注入 `space_id`，查询时自动过滤 |

---

## 🛠️ 技术栈

| 层级            | 技术                              | 版本  |
| --------------- | --------------------------------- | ----- |
| **后端框架**    | FastAPI                           | 0.115 |
| **ORM**         | SQLAlchemy 2.0 (async)            | 2.0   |
| **数据库**      | SQLite (开发) / PostgreSQL (生产) | —     |
| **认证**        | JWT (HS256)                       | —     |
| **模板引擎**    | Jinja2 (Sandboxed)                | 3.1   |
| **前端框架**    | React 18 + TypeScript             | 18    |
| **UI 组件**     | Ant Design 5                      | 5.20  |
| **状态管理**    | Zustand                           | 4.5   |
| **数据请求**    | TanStack React Query              | 5.x   |
| **HTTP 客户端** | Axios                             | 1.7   |
| **构建工具**    | Vite                              | 5.x   |
| **加密**        | AES-256-GCM (cryptography)        | —     |
| **密码哈希**    | bcrypt                            | —     |

---

## 🚀 快速开始

### 环境要求

- Python >= 3.10
- Node.js >= 18
- npm

### 1. 克隆并安装

```bash
git clone https://github.com/ambyron/AgentTestMate.git
cd AgentTestMate
```

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
python cli.py serve
```

首次启动会自动创建 SQLite 数据库和初始化表结构，并创建默认管理员账号。

> 默认监听 `http://localhost:8080`，API 文档访问 `http://localhost:8080/docs`

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:3000` 即可使用。

### 4. 默认管理员

| 用户名  | 密码       |
| ------- | ---------- |
| `admin` | `admin123` |

---

## 📚 使用指南

### 完整评测流程

```
1. 创建智能体  →  2. 导入数据集  →  3. 配置评估规则
                                        ↓
4. 查看评测报告  ←  执行评测任务  ←  创建评测任务
```

**步骤说明：**

1. **智能体** — 配置待评测 AI Agent 的 API 地址、认证方式和请求模板
2. **数据集** — 创建测试用例（输入 + 预期输出），或批量导入
3. **评估规则** — 配置评分维度、规则类型（精确匹配/关键词/AI 评分等）
4. **评测任务** — 选择智能体、数据集和规则，创建并启动任务
5. **结果分析** — 查看详细的评分明细、通过率，导出报告
6. **人工审核** — 对结果进行人工标注，持续优化评估体系

### CLI 工具

```bash
cd backend
python cli.py --help
python cli.py list agents        # 查看智能体列表
python cli.py list tasks         # 查看任务列表
python cli.py list datasets      # 查看数据集列表
python cli.py import-dataset --file data.json   # 导入数据集
python cli.py report --task <id> --format html  # 导出报告
```

---

## 🔒 安全特性

AgentMate 内置了多层安全防护：

| 类别         | 措施                                        |
| ------------ | ------------------------------------------- |
| **认证**     | JWT Token（2h 过期）+ bcrypt 密码哈希       |
| **授权**     | 基于空间（Space）的数据隔离，admin 提权校验 |
| **API 安全** | 字段白名单防止 Mass Assignment              |
| **文件上传** | 5MB 上限、文件类型魔数校验、速率限制        |
| **凭据加密** | API Key 使用 AES-256-GCM 加密存储           |
| **日志脱敏** | 自动过滤 Token / API Key / 密码等敏感信息   |
| **模板安全** | Jinja2 SandboxedEnvironment 防止模板注入    |
| **脚本沙箱** | AST 级别安全检查 + 执行超时限制             |

---

## 🤝 贡献指南

欢迎提交 Pull Request 和 Issue！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feat/my-feature`
3. 提交修改：`git commit -am 'feat: add some feature'`
4. 推送分支：`git push origin feat/my-feature`
5. 提交 Pull Request

代码规范：

- Python 代码遵循 `PEP 8`
- 前端代码遵循项目内的 TypeScript 风格
- 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范

---

## 📄 许可证

[Apache License 2.0](LICENSE)

```
Copyright 2026 AgentTestMate Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

<div align="center">
  <sub>Built with ❤️ for the AI Agent community</sub>
</div>
