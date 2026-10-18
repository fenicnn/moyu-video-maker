---
name: moyu-video-maker
description: 从本地视频、公开视频链接或双语字幕制作 Moyu Studio 英语学习资源；能发现或生成双语字幕，按用户选择的四级、六级、雅思等范围筛选语境词汇，并严格交付单个 MP4、高亮 SRT 和词汇 JSON。用于单集、批量、只有视频或只有链接的英文素材制作；不用于绕过 DRM、付费墙或下载未获授权的内容。
metadata:
  short-description: 从视频或链接生成 MP4、高亮双语字幕与词汇 JSON
---

# Moyu Video Maker

把本地视频、用户提供的公开视频链接或现成双语 SRT 制作为 Moyu Studio 可直接使用的英语学习资源。保留原技能的高亮、词汇映射、幂等 MP4 和批量审计能力，并增加字幕发现、云端转写兜底、学习范围交互和严格三文件交付。

## 路径与环境体检

- **技能目录**是本 `SKILL.md` 所在目录，只用于读取脚本和参考文件，不在其中生成缓存、日志或成品。
- **工作区**是用户当前项目或明确指定的制作目录。默认缓存放在 `<工作区>/.moyu-work/<episode>/`，成品放在 `<工作区>/output/<episode>/`；用户指定位置时优先采用。
- 从工作区调用技能目录中的脚本，使用绝对脚本路径，并显式传入绝对 `--work-dir`、`--output-dir`（对应命令支持时）。不要为了调用脚本切换到技能安装目录。下面示例中的 `scripts/` 均应替换为技能目录下的绝对路径。
- 高亮脚本已内置，无需另装高亮技能。

首次制作或依赖报错时，先执行只读体检：

```bash
python3 /absolute/path/to/moyu-video-maker/scripts/doctor.py --source local
```

链接使用 `--source url`，已有字幕使用 `--source srt`。体检检查 Python、FFmpeg 和 ffprobe，只有链接任务要求 yt-dlp。缺失项会说明受影响步骤并返回非零状态；修复后再继续。体检不自动安装软件、不读取密钥、不调用云端或本地 AI。云端能力与授权由当前代理另行确认。

## 不可变约束

- AI 标词、短语边界、翻译、转写校订和语境释义只能由当前用户已授权的云端 AI 完成。
- 绝对禁止探测、启动或调用任何本地大模型或本地语音模型，包括 Ollama、LM Studio、llama.cpp、本地 Whisper 和 localhost OpenAI-compatible 服务。
- 禁止用本地词典、离线词库、在线词典或 term-only 翻译生成/兜底 `partOfSpeech` 与 `meaning`。等级词表只可辅助难度筛选。
- 不绕过 DRM、登录、验证码、会员或付费限制。链接仅处理用户有权访问且下载工具支持的内容。
- 网络搜索、第三方账号、下载配额和云端付费步骤必须遵守当前授权；没有授权时先说明并停在可复用的工作缓存处。

## 先确认词汇范围

用户已经说明“四级、六级、雅思”等范围时直接采用，不重复提问。否则在第一次语义筛词前主动询问：

> 这次按什么范围筛选重点词汇？例如“四级”“六级”“雅思 7 分”“日常口语”，也可以自定义。

范围支持：日常基础、四级、六级、考研、雅思、托福、自定义。批量任务只问一次并整批复用。用户没有回答时可以完成下载和字幕发现，但暂停语义筛词，不擅自猜测。

执行筛词时读取 [references/learning-profile.md](references/learning-profile.md)。

## 输入路由

1. **用户给公开视频链接**：取得必要网络授权后，用 `prepare_source.py --url` 下载最高 1080p 视频并同时尝试人工/自动字幕。
2. **用户只给本地视频**：用 `prepare_source.py --video` 盘点同目录字幕、提取文本内嵌字幕并计算 OpenSubtitles Hash。
3. **用户已给双语 SRT**：跳过字幕获取，直接验证字幕后进入标词流程。
4. **用户指定一段集数**：先只读审计，再逐集补缺失产物，最后严格复查；同一学习范围默认应用到整批。

缺少可用双语字幕时读取 [references/subtitle-acquisition.md](references/subtitle-acquisition.md)，按“本地双语 → 本地英文 → 内嵌文本 → 来源平台字幕 → OpenSubtitles 候选 → 用户导入 → 云端转写”的顺序处理。网络字幕必须验证版本、时长和时间轴，不能因标题相同就直接采用。

## 链接或视频准备

公开视频链接：

```bash
python3 scripts/prepare_source.py \
  --url 'https://...' \
  --work-dir /path/to/.moyu-work/item \
  --stem source \
  --network-policy allow
```

本地视频：

```bash
python3 scripts/prepare_source.py \
  --video /path/to/source.mkv \
  --work-dir /path/to/.moyu-work/item
```

脚本只执行确定性媒体操作，不调用任何 AI。`source-manifest.json` 记录视频、同目录字幕、平台字幕、内嵌轨和候选来源。原始资源、候选字幕、音频切片、提示词和日志全部保存在工作目录，不放进最终交付目录。

## 双语字幕要求

- 英文在上、中文在下；cue 序号和时间轴有效且递增。
- 有可信英文时间轴时，保留其 cue 边界，由云端 AI 逐 cue 生成符合语境的中文。
- 分别下载的中英文字幕只有在 cue 与时间轴高度一致时才可合并。
- 无字幕时才调用云端语音识别；长视频按服务限制切片，合并时处理重叠并复核人名、地名和连续剧情。
- 普通歌词网页不能直接作为歌曲时间轴；歌曲优先使用来源页字幕、内嵌字幕或用户合法提供的 LRC/SRT/VTT。

## 单集制作流程

### 1. 初始化

```bash
python3 scripts/moyu_pipeline.py init \
  --srt /path/to/bilingual.srt \
  --episode e04 \
  --work-dir /path/to/.moyu-work/e04 \
  --video /path/to/source.mp4
```

`.moyu-work/<episode>` 保存 `srt.original.txt`、words/corrections/glosses 模板等中间状态。

### 2. 云端 AI 标词与翻译修正

AI 阅读完整双语字幕，按已确认的学习范围和实际学习价值输出：

```json
{
  "words": {"字幕序号": ["英文原样词汇", "英文原样短语"]},
  "corrections": {"需要修正的字幕序号": "修正后的整句中文"}
}
```

导入前验证 term 是对应英文 cue 的原样连续子串：

```bash
python3 scripts/moyu_pipeline.py apply-selection \
  --input /path/to/selection.json \
  --episode e04 \
  --work-dir /path/to/.moyu-work/e04
```

### 3. 生成高亮 SRT 与词汇 JSON

```bash
python3 scripts/moyu_pipeline.py finish \
  --srt /path/to/bilingual.srt \
  --episode e04 \
  --work-dir /path/to/.moyu-work/e04 \
  --video /path/to/source.mp4 \
  --output-dir /path/to/.moyu-work/e04/generated \
  --no-prompt
```

`vocab` 从高亮 SRT 中的彩色标签直接生成词汇 JSON 骨架。当前云端 AI 必须根据每个 cue 的完整中英文语境回填 `phonetic / partOfSpeech / meaning`；目标 cue 不足以判断时才读取相邻 cue。回填失败必须重试或停止，不得用词典或本地模型凑齐。

### 4. 严格发布三个文件

先确认 MP4、高亮 SRT 和已回填完整的 JSON 都在工作目录，通过后发布到一个单独成品目录：

```bash
python3 scripts/publish_deliverables.py \
  --video /path/to/generated/source.mp4 \
  --srt /path/to/generated/highlighted.srt \
  --vocab /path/to/generated/vocabulary.json \
  --output-dir /path/to/final/lesson \
  --stem lesson
```

最终目录必须且只能包含：

```text
lesson/
├── lesson.mp4
├── lesson.srt
└── lesson.json
```

发布脚本要求 ffprobe 可用，验证 MP4 音视频流和时长、每个 cue 的中英文内容、合法且有序的序号和时间轴、字幕不超出视频时长、词汇 JSON 的完整字段，以及 JSON `cueIndex + term` 与 SRT 高亮序列逐项一致。已有目录含额外文件时拒绝清理或覆盖；不要删除用户文件。更新已存在的三个规范文件需要显式 `--force`。

## 标词与释义规则

- 选择可迁移复用的单词、固定搭配、短语动词、习语和句型核心；跳过专有名词和明显基础词，除非当前语境存在值得学习的熟词生义。
- 短语优先于其内部单词，避免嵌套；去重范围仅限同一 cue，同一规范化词形只保留首次出现。
- 不得跨 cue 或按整集词表去重。某词一旦入选为重点词，后续不同 cue 再次出现同一规范化词形时必须再次高亮，并为每个 cue 分别生成 `cueIndex + term` JSON 条目；term 保留当前 cue 的原始大小写。
- 禁止把普通整句话当重点短语。固定话语习语如 `Over my dead body` 可以保留。
- 不按末尾词性机械判残缺。`look around`、`come across` 等可以以小品词结尾；`take a lot of` 在 `take a lot of courage` 中缺少中心成分，才属于残缺。
- term 必须保留字幕原始大小写、时态、单复数、连字符和重音字符，不能改为词典原形。
- `meaning` 必须能替换回当前句而不改变句意；不能填词典首义、整句机械翻译或上一项释义。
- `partOfSpeech` 按当前 cue 中的实际用法填写；短语使用 `phrase`。
- **重要程度优先**：按可迁移复用价值、目标学习范围、语境代表性、熟词生义价值和固定搭配完整性综合判断；高价值才保留。
- **禁止数量驱动**：不得按视频时长、每分钟密度、固定数量、最低数量或词频配额筛选，也不得为了达到某个数量补入低价值词。最终数量只能是质量筛选后的自然结果。
- 词频只能作为了解常见程度的背景信息，不能单独决定入选；低频但高度可迁移、语境典型的表达可以保留，高频但过于基础或低收益的表达应跳过。

## 词汇字段映射

词汇对象必须包含：

```json
{
  "cueIndex": 62,
  "term": "原样高亮文本",
  "phonetic": "",
  "partOfSpeech": "phrase",
  "meaning": "当前语境释义"
}
```

- `cueIndex` 直接取 SRT 块第一行的数字，不生成 ID、时间戳 ID 或 `term-0`。
- `term` 直接取 `<font color="...">...</font>` 或彩色 `<span>` 中的英文。
- JSON 顺序必须与 SRT cue 顺序、cue 内高亮出现顺序完全一致。
- 输入是无高亮普通 SRT 时不得凭空生成 vocabulary。

解析或导入异常时读取 [references/studio-vocabulary-contract.md](references/studio-vocabulary-contract.md)。

## 视频规范与幂等行为

- 输入已经是有效 MP4 时默认复用，不重复转码。
- 非 MP4：H.264/HEVC 优先复制视频流并标记 `avc1/hvc1`；其他编码转 HEVC；音频使用 AAC，输出加 `+faststart`。
- 已存在且有效的规范 MP4 必须跳过；已存在但无效时停止并报告，不静默覆盖或生成编号副本。
- 编码或播放器兼容问题读取 [references/video-transcoding.md](references/video-transcoding.md)。

## 批量任务

开始前：

```bash
python3 scripts/audit_media_batch.py /path/to/season --episodes 4-10
```

只补缺失规范 MP4：

```bash
python3 scripts/ensure_canonical_mp4.py /path/to/season --episodes 4-10
```

每集完成语义制作和三文件发布后，再运行严格审计。旧式剧集目录仍可使用：

```bash
python3 scripts/audit_media_batch.py /path/to/season --episodes 4-10 --strict
```

只有用户指定的完整范围全部通过才能报告批次完成。冗余文件只报告，不自动删除。

## 资源

- `scripts/prepare_source.py`：从本地视频或公开 URL 建立工作缓存，下载最高 1080p 视频、发现/提取字幕并记录来源。
- `scripts/moyu_pipeline.py`：初始化、导入 AI 选择、高亮、词汇 JSON 骨架、转码、完成与状态检查。
- `scripts/publish_deliverables.py`：发布并严格审计只含 MP4、高亮 SRT、词汇 JSON 的成品目录。
- `scripts/audit_media_batch.py`：旧式按集目录批量完成矩阵。
- `scripts/ensure_canonical_mp4.py`：幂等生成规范 MP4。

## 修改后验证

```bash
python3 scripts/doctor.py --help
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/prepare_source.py --help
python3 scripts/moyu_pipeline.py --help
python3 scripts/publish_deliverables.py --help
python3 scripts/audit_media_batch.py --help
python3 scripts/ensure_canonical_mp4.py --help
```
