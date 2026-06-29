---
name: meeting-audio-local-workflow
description: 本地中文长会议录音处理工作流：使用 FunASR SenseVoiceSmall + FSMN-VAD + CAM++ 转写 1-2 小时会议录音，再用 Apple Silicon MLX + Qwen2.5-7B-Instruct-4bit 分块整理成会议纪要。适用于中文会议录音、访谈、座谈会、长音频转文字、转写稿整理、离线本地模型处理。
---

# 本地中文会议录音转写与纪要整理工作流

当用户要求“把录音转文字并整理”“会议录音出纪要”“长音频中文转写”“本地模型整理转写稿”时，使用本 skill。

## 已验证环境

- 机器：Apple Silicon，实测 Apple M4 / 16GB 可用。
- ASR：`FunASR + iic/SenseVoiceSmall + fsmn-vad + cam++`。
- LLM：`MLX + mlx-community/Qwen2.5-7B-Instruct-4bit`。
- 已验证 7B 模型峰值内存约 4.43GB，生成速度约 20+ tokens/s。
- Ollama 在当前机器曾出现 CLI 卡 dyld、服务不监听 `11434`，不要优先走 Ollama。

## 一键工作流

```bash
cd /Users/qing/code/GenericAgent
skills/meeting-audio-local-workflow/run_meeting_workflow.sh ~/Downloads/0602.mp3
```

默认输出目录：

```text
~/Downloads/meeting_transcript_<音频文件名>/
```

核心产物：

```text
<stem>.txt                                  # 带时间戳/说话人标签的原始转写
<stem>.md                                   # Markdown 转写稿
<stem>.srt                                  # 字幕
<stem>.segments.json                        # 结构化分段
<stem>.raw.json                             # FunASR 原始输出
<stem>_本地模型整理_Qwen7B_清洗版.md          # 推荐查看的最终纪要
<stem>_本地模型整理_Qwen7B.partial.md        # 分段整理草稿，便于追溯
<stem>_workflow.log                         # 工作流日志
```

## 只整理已有转写稿

如果已经有 `.txt` 转写稿，跳过 ASR：

```bash
cd /Users/qing/code/GenericAgent
skills/meeting-audio-local-workflow/run_meeting_workflow.sh \
  --transcript ~/Downloads/meeting_transcript_0602/0602.txt
```

## 常用参数

```bash
skills/meeting-audio-local-workflow/run_meeting_workflow.sh ~/Downloads/meeting.mp3 \
  -o ~/Downloads/meeting_transcript_custom \
  --language zh \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --max-chars 7200 \
  --max-tokens-chunk 1800 \
  --max-tokens-final 2600
```

参数建议：

- `--language zh`：普通话中文会议首选。
- `--language auto`：多语种或不确定语言时使用。
- `--max-chars 7000-8500`：长会议分块大小；7B 推荐 7200 左右。
- `--max-tokens-final 2600+`：最终纪要更完整，但耗时更长。
- 若 7B 下载失败或速度不可接受，可临时改为 `mlx-community/Qwen2.5-3B-Instruct-4bit`，但最终合并质量会下降。

## 分阶段命令

### 1. 只做 ASR 转写

```bash
cd /Users/qing/code/GenericAgent
scripts/asr/funasr_meeting.sh ~/Downloads/0602.mp3 -o ~/Downloads/meeting_transcript_0602 --language zh
```

### 2. 只做本地 LLM 整理

```bash
cd /Users/qing/code/GenericAgent
source .venv_mlx/bin/activate
python skills/meeting-audio-local-workflow/local_mlx_meeting_summarize.py \
  ~/Downloads/meeting_transcript_0602/0602.txt \
  -o ~/Downloads/meeting_transcript_0602/0602_本地模型整理_Qwen7B.md \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --max-chars 7200 \
  --max-tokens-chunk 1800 \
  --max-tokens-final 2600
```

## 质量控制流程

1. **先确认音频存在和时长**：`ffprobe` 或 `ls -lh`。
2. **ASR 完成后检查**：确认 `.txt/.md/.srt/.segments.json/.raw.json` 都生成，抽查首尾内容。
3. **LLM 整理后检查**：优先打开 `_清洗版.md`，再看 `.partial.md` 追溯来源。
4. **正式材料必须复核**：ASR 对人名、地名、单位名、年份、数字、专有名词可能误识别；涉及责任、时间、数据的内容要回听核对。
5. **不要把模型输出当事实来源**：最终纪要只能来自转写稿；不确定内容标 `【待核】`。

## 故障处理

- `ffmpeg` 报坏帧：ASR 脚本已使用 `+discardcorrupt` 和 `ignore_err`，通常可继续处理。
- FunASR MPS 失败：默认用 CPU，当前最稳；不要强行切 MPS。
- HuggingFace 下载慢：可重跑，`snapshot_download` 会续传；必要时设置 HF_TOKEN，但不要打印 token。
- LLM 输出被包进 ```markdown 代码块：使用一键脚本会生成 `_清洗版.md`。
- 纪要过粗：提高 `--max-tokens-chunk` / `--max-tokens-final`，或查看 `.partial.md` 手工补充。

## 当前机器已知路径

```text
FunASR venv: /Users/qing/code/GenericAgent/.venv_funasr
MLX venv:    /Users/qing/code/GenericAgent/.venv_mlx
ASR script:  /Users/qing/code/GenericAgent/scripts/asr/funasr_meeting.sh
Skill dir:   /Users/qing/code/GenericAgent/skills/meeting-audio-local-workflow
```
