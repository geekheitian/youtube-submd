# youtube-submd / bestpartners_tool

## 1. 项目概述

### 目标

这是一个用于 **从 YouTube 频道抓取最新视频字幕并生成摘要** 的命令行工具。

当前实现已经从最初的 BestPartners 专用脚本，演进为一个 **支持频道跟踪的通用字幕摘要工具**：

- 可抓取指定频道最新视频
- 可下载并清洗字幕
- 可将字幕保存为 Markdown
- 可生成适合 Obsidian 保存的结构化摘要
- 可按频道组织输出目录和元数据
- 可按 `source/video_id` 做幂等去重

### 当前已验证特性

1. 获取频道最新视频列表（默认 10 个）
2. 下载视频字幕，优先级：`zh-Hans > zh-Hant > en`
3. 将 VTT 字幕清洗为连续文本并保存为 Markdown
4. 使用 `MiniMax` 生成结构化中文摘要
5. `DashScope` 作为次级 fallback
6. 使用 `--force` 明确重处理已处理视频
7. 通过 `channel` / `channel_url` 在文件中保留频道上下文
8. 通过环境变量和 CLI 覆盖输出目录配置

---

## 2. 当前处理流程

### 2.1 视频获取

输入：YouTube 频道 URL，例如：

- `https://www.youtube.com/@BestPartners/videos`

输出：

- 视频标题
- 视频 ID
- 上传日期

### 2.2 字幕处理

当前字幕链路已经拆分为两个显式阶段：

1. **字幕清洗阶段**
   - 读取原始 VTT 文件
   - 去掉时间轴、序号、`WEBVTT` 头和语言标签
   - 提取纯文本行
   - 合并为清洗后的字幕文本

2. **字幕输出阶段**
   - 将清洗后的文本保存为 Markdown
   - 在 frontmatter 中记录：
     - `title`
     - `source`
     - `channel`
     - `channel_url`
     - `language`

### 2.3 摘要生成

当前摘要链路优先级如下：

1. **MiniMax**
   - 使用 `POST /v1/chat/completions`
   - 模型：`MiniMax-Text-01`
   - 用于生成结构化中文摘要

2. **DashScope**
   - 当 MiniMax 不可用时尝试使用

3. **基础摘要 fallback**
   - 当 AI provider 都不可用时，生成说明文字 + 字幕预览

### 2.4 输出格式

当前默认摘要格式不是长段落，而是 **结构化 Markdown 笔记**，固定包含：

- `### 核心主题`
- `### 关键观点`
- `### 重要结论`
- `### 可行动点`

这更适合在 Obsidian 中阅读和复用。

---

## 3. 目录结构

默认情况下，输出会写到：

```text
{BASE_DIR}/{CONTENT_SUBDIR}/{频道名}/
├── 字幕/
└── 摘要/
```

例如默认 BestPartners：

```text
/Users/yangkai/Nutstore Files/mba/obsidian/第二大脑/01-内容/BestPartners/
├── 字幕/
└── 摘要/
```

其中：

- `BASE_DIR` 可配置
- `CONTENT_SUBDIR` 可配置
- `{频道名}` 由频道 URL 自动推导

---

## 4. 命令行接口

```bash
# 默认运行（使用默认频道与默认输出目录）
python3 bestpartners_tool.py

# 预览模式（不下载字幕）
python3 bestpartners_tool.py --dry-run

# 指定处理数量
python3 bestpartners_tool.py --limit 5

# 处理其他频道
python3 bestpartners_tool.py --channel "https://www.youtube.com/@其他频道/videos"

# 强制重新处理已存在的视频
python3 bestpartners_tool.py --force

# 覆盖输出根目录
python3 bestpartners_tool.py --base-dir "/path/to/vault"

# 覆盖内容子目录
python3 bestpartners_tool.py --content-subdir "01-内容"
```

---

## 5. 配置方式

### 5.1 环境变量

| 变量 | 用途 | 必需 |
|------|------|------|
| `MINIMAX_API_KEY` | MiniMax 摘要生成 | 推荐 |
| `MINIMAX_BASE_URL` | MiniMax API 地址，默认 `https://api.minimax.chat/v1` | 可选 |
| `DASHSCOPE_API_KEY` | DashScope 标题翻译 / 摘要 fallback | 可选 |
| `YTSUBMD_BASE_DIR` | 输出根目录 | 可选 |
| `YTSUBMD_CONTENT_SUBDIR` | 内容子目录，默认 `01-内容` | 可选 |
| `YTSUBMD_DEFAULT_CHANNEL_URL` | 默认频道 URL | 可选 |
| `YTSUBMD_DEFAULT_CHANNEL_NAME` | 当 URL 无法推导频道名时的默认频道名 | 可选 |
| `YTSUBMD_DEFAULT_LIMIT` | 默认处理数量 | 可选 |

### 5.2 CLI 覆盖优先级

如果同时存在环境变量和 CLI 参数：

- CLI 优先
- 环境变量次之
- 最后才使用内置默认值

---

## 6. 幂等与重处理规则

### 去重规则

工具当前通过摘要文件中的以下元数据进行去重：

```yaml
source: https://www.youtube.com/watch?v=<video_id>
```

也就是说，当前幂等主键是：

- `source / video_id`

### 重处理规则

- 默认运行：如果该视频已存在摘要文件，则跳过
- `--force`：即使已存在，也会重新下载字幕并重新生成摘要

---

## 7. 核心函数 / 结构

| 函数 / 结构 | 功能 |
|------|------|
| `AppConfig` | 应用级配置，承载默认目录、默认频道、provider 地址等 |
| `ChannelContext` | 频道级上下文，承载频道名、URL、字幕目录、摘要目录 |
| `get_channel_videos()` | 获取频道视频列表 |
| `get_available_subtitles()` | 检查可用字幕语言 |
| `download_subtitle()` | 下载字幕文件 |
| `prepare_subtitle_text()` | 执行字幕清洗阶段 |
| `convert_subtitle_to_md()` | 将清洗后的字幕文本保存为 Markdown |
| `translate_to_chinese()` | 标题翻译（可选） |
| `generate_summary()` | 摘要入口，优先 MiniMax，其次 DashScope |
| `save_summary()` | 保存摘要文件 |
| `process_video()` | 单视频处理流程 |

---

## 8. 技术栈

- **语言**: Python 3.11+
- **视频获取**: `yt-dlp`
- **AI 摘要**: MiniMax (`MiniMax-Text-01`)
- **可选 fallback**: DashScope Qwen
- **存储**: Markdown 文件

---

## 9. 当前已知限制

1. 默认输出路径仍然带有一个内置本地默认值，但现在已经可通过环境变量或 CLI 覆盖
2. 频道上下文已经结构化，但更进一步的配置管理仍可继续完善
3. 字幕清洗已拆层，但“智能标点 / 语义分段”尚未单独实现为独立增强步骤
4. 目前还没有补齐自动化测试

---

## 10. 后续建议

建议按以下顺序继续推进：

1. 增加最小测试覆盖
2. 继续增强字幕清洗质量（智能标点、语义分段）
3. 进一步完善 README 和使用示例
4. 视需要增加更细粒度的 CLI 模式，例如：
   - `--subs-only`
   - `--summary-only`
   - `--channel-name`
