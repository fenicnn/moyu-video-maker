# 字幕获取与验证协议

只在输入缺少可用双语 SRT 时读取本文件。目标是复用可信字幕，无法验证时才进行云端转写。

## 来源顺序

1. 与视频同目录的双语 SRT。
2. 同目录的英文字幕；保留其时间轴，由当前授权的云端 AI 生成中文。
3. 视频容器中的文本字幕轨；位图字幕默认不 OCR。
4. 用户给出的来源网址：优先人工英文字幕，其次平台自动英文字幕。
5. OpenSubtitles：优先 `moviehash` 完全匹配，再比较剧名、季集数、时长、帧率和发布版本。
6. 用户从 Trancy 或其他合法来源导出的 SRT/VTT/ASS/CSV；无时间轴的 PDF/纯文本不能直接作为最终字幕。
7. 以上全部失败后，调用用户已授权的云端语音识别。

不得爬取需要绕过登录、验证码、付费墙或 DRM 的内容。不得把 Trancy、Google/YouTube 或任意字幕站点假定为稳定公开 API。YouTube 官方字幕下载接口通常要求视频编辑权限；公开视频字幕可在用户提供来源网址时尝试用 yt-dlp 获取，但失败后应降级到其他来源而不是反复请求。

## 本地确定性准备

```bash
python3 scripts/prepare_source.py \
  --video /path/to/video.mkv \
  --work-dir /path/to/work
```

对用户明确给出的公开视频网址，取得网络授权后：

```bash
python3 scripts/prepare_source.py \
  --url 'https://...' \
  --work-dir /path/to/work \
  --stem source \
  --network-policy allow
```

如已设置 `OPENSUBTITLES_API_KEY`，可额外搜索候选：

```bash
python3 scripts/prepare_source.py \
  --video /path/to/video.mkv \
  --work-dir /path/to/work \
  --title 'Friends S02E04' \
  --network-policy allow \
  --search-opensubtitles
```

脚本仅搜索并记录候选，不自动消耗字幕下载配额。下载候选前应先确认来源和匹配度。

## 候选字幕门禁

按以下证据排序，不以“同名”作为充分条件：

- 文件哈希完全一致：最高可信度。
- 剧名、季数、集数一致，且时长误差不超过 2 秒：高可信度。
- 发布版本、帧率、片头/回顾结构一致：提高可信度。
- 只有标题或模糊关键词一致：低可信度，不得自动采用。

检查首段、中段、末段，区分固定偏移和逐渐漂移。只允许在证据充分时修正统一偏移或简单线性漂移；需要逐句大改说明版本不匹配，应丢弃候选。

分别下载的英文和中文字幕只有在 cue 与时间轴高度一致时才可合并。通常应保留可信英文时间轴，再由云端 AI 逐 cue 生成语境中文，避免两套字幕错位。

## 云端转写兜底

- 绝不调用本地 Whisper、Ollama、LM Studio、llama.cpp 或 localhost 模型。
- 使用云端语音识别时保留分段时间戳；长视频按服务限制切片，并保留少量重叠以防边界漏词。
- 合并时去除重叠重复，确保 cue 时间递增且不超出视频时长。
- 人名、地名和连续剧情需要全片一致性复核。
- 完成英文稿后再翻译中文，不让翻译反向改写英文时间轴。

## 工作缓存

原始字幕、候选 JSON、音频切片、提示词、日志和来源记录只放在工作目录，例如：

```text
.moyu-work/e01/
├── source-manifest.json
├── source/
├── subtitles/
├── srt.original.txt
└── ...
```

这些都不是交付物，最终目录不得包含它们。
