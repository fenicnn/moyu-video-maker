# Moyu Video Maker

将英文视频、公开视频链接或双语字幕制作成 Moyu 英语学习资源。

支持日常口语、四级、六级、考研、雅思、托福及自定义范围；输出同名 MP4、高亮双语 SRT 和 schemaVersion 2 词汇 JSON，可在 [Moyu 本地播放器](https://muoyu.cn/video-player?tab=local) 导入。

## 安装与使用

本仓库根目录就是技能目录。下载或克隆后，将整个目录放入支持本技能的代理工具的技能目录，文件夹命名为 `moyu-video-maker`。Codex 的默认位置为 `~/.codex/skills/moyu-video-maker`。重新打开会话以加载新技能。

已有本地仓库时，也可创建软链接（目标位置必须尚不存在）：

```bash
ln -s /absolute/path/to/moyu-video-maker ~/.codex/skills/moyu-video-maker
```

向代理提交素材，并使用以下指令：

> 使用 $moyu-video-maker 处理我提供的视频，按雅思 7 分筛选重点词汇，生成可导入 Moyu 的 MP4、高亮双语 SRT 和词汇 JSON。

## 运行依赖

- Python 3.10+；处理脚本仅使用 Python 标准库。
- FFmpeg / ffprobe：媒体处理与最终音视频流校验。
- yt-dlp：仅下载公开视频链接时需要。
- 用户已授权的云端 AI：筛词、翻译、语境释义；缺少字幕时可能需要云端转写服务。

这是一套由 AI 代理编排的技能，不是独立网页服务。Python 脚本负责确定性处理，不能单独完成 AI 筛词和释义。云端调用可能产生费用。仅处理有权使用的素材。

完整操作规范见 [SKILL.md](SKILL.md)。字幕高亮脚本已内置，无需安装其他技能。

## 交付格式

```text
lesson/
├── lesson.mp4
├── lesson.srt
└── lesson.json
```

视频与字幕分开交付，不将字幕烧录进视频。词汇协议见 [播放器数据约定](references/studio-vocabulary-contract.md)。

## 开发与验证

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/prepare_source.py --help
python3 scripts/moyu_pipeline.py --help
python3 scripts/publish_deliverables.py --help
python3 scripts/audit_media_batch.py --help
python3 scripts/ensure_canonical_mp4.py --help
```

## 迁移来源

从 `fenicnn/agent-skills` 的 `moyu-vocab-pipeline` 拆出，源提交 `65f4db4`；同时纳入该仓库的 `srt-vocab-highlight/scripts/srt_highlight_full.py`，消除相邻技能依赖。

技能名称更新为 `moyu-video-maker`；保留脚本命令、工作缓存格式和 schemaVersion 2 数据协议。旧技能暂时保留，后续维护以本仓库为准。网站入口接入和在线制作服务不包含在本次拆分中。
