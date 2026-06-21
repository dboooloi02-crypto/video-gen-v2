# 🎬 AI 英语学习短视频生成器 v2

> 作者：小宅 · 2026.6.21

一键生成 **双语学习短视频** — AI 写对话 → TTS 配音 → 字幕动效渲染 → MP4 输出。

```
$ pip install -r requirements.txt
$ python main.py --topic "在便利店偶遇朋友"
→ output/demo.mp4 ✅
```

---

## 项目背景

面向英语学习类短视频创作者（抖音 / B站 / 小红书 / YouTube Shorts），省去人工写稿→配音→剪辑的繁琐流程，一条命令出片。

## 核心能力

| 能力 | 说明 |
|------|------|
| **AI 剧本生成** | 接入任意 OpenAI 兼容 API（默认免费 ZhipuAI GLM-4-Flash），自动生成中英双语对话+关键词 |
| **TTS 配音** | 基于 edge-tts，支持中/英/日/韩多语种，字级别时间戳对齐 |
| **字幕动效** | PIL + NumPy 逐帧渲染，渐入/渐出/关键词放大发光效果 |
| **多种模板** | `english_learning` / `podcast` / `tiktok` / `mixed_inline` |
| **中英混排** | 特有 mixed_inline 模式，中英夹杂的真实职场/生活对话场景 |
| **API + 前端** | FastAPI 后台 + index.html Web 界面，Docker 一键部署 |
| **Docker 就绪** | 含 Dockerfile + docker-compose.yml，云服务器直接跑 |
| **零成本体验** | 默认智谱 GLM-4-Flash 免费调用，内置 demo 模式无需 API Key |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 下载字体

```bash
python setup_fonts.py
```

### 3. 不配 API Key 试跑 demo

```bash
python main.py --mode demo
```

等待几十秒 → `output/demo.mp4` 生成完毕。

### 4. 配 API Key 全功能模式

复制 `.env.example` 为 `.env`，填入你的 API Key：

```env
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
LLM_MODEL=glm-4-flash
```

生成视频：

```bash
python main.py --topic "在便利店偶遇朋友"
```

## CLI 用法

```bash
# AI 全流程（需 LLM_API_KEY）
python main.py --topic "职场英语面试" --template tiktok

# 选择模板
python main.py --topic "日常对话" --template podcast
python main.py --topic "机场问路" --template english_learning

# 中英混排模式（展示职场/生活中英混说场景）
python main.py --mode mixed --input my_scene.json

# 使用预制脚本（跳过 AI 生成）
python main.py --mode script --input my_script.json

# 批量生成
python main.py --mode batch --input batch_jobs.json

# 查看可用模板
python main.py --list-templates
```

## API 服务模式

```bash
pip install -r requirements_server.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000` → Web 界面操作。

### API 接口

```
POST /generate    — 提交视频生成任务
GET  /status/{id} — 查询任务状态
GET  /download/{id} — 下载生成视频
GET  /templates   — 查看可用模板
GET  /health      — 健康检查
```

## Docker 部署

```bash
export LLM_API_KEY=your_key_here
docker compose up -d
```

访问 `http://localhost:8000`

## 项目结构

```
video_gen_v2/
├── main.py                  # CLI 入口
├── pipeline.py              # 全流程编排
├── server.py                # FastAPI Web 服务
├── config.py                # 中心配置
├── index.html               # Web 前端
├── setup_fonts.py           # 字体下载与环境检测
├── Dockerfile               # 容器化部署
├── docker-compose.yml       # Docker Compose
├── .env.example             # 环境变量模板
├── src/
│   ├── generator/           # AI 对话剧本生成
│   ├── tts/                 # 语音合成 (edge-tts)
│   ├── subtitle/            # 字幕时间线构建
│   ├── renderer/            # 逐帧渲染 (PIL + NumPy)
│   ├── templates/           # 视频模板
│   └── export/              # MP4 输出 (moviepy)
├── output/                  # 生成视频目录
└── fonts/                   # 字体目录
```

## 支持模板

| 模板名 | 说明 | 适用场景 |
|--------|------|---------|
| `english_learning` | 经典中英对照字幕 + 关键词高亮 | 通用英语学习视频 |
| `podcast` | 大字幕 + 深色背景，对话感强 | 听力训练 / 播客风 |
| `tiktok` | 竖屏 9:16 极简风，关键词特写 | 短视频平台 |
| `mixed_inline` | 中英混排，职场/生活场景 | 真实对话场景还原 |

## 技术栈

- **渲染**: Pillow + NumPy（不依赖 GPU）
- **AI**: OpenAI 兼容 API（智谱 / DeepSeek / OpenAI）
- **TTS**: Microsoft Edge TTS（edge-tts）
- **输出**: MoviePy + FFmpeg
- **服务**: FastAPI + Uvicorn

## 许可

MIT License © 2026 小宅
