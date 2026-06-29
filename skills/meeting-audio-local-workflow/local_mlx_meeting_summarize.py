#!/usr/bin/env python3
"""Use local MLX LLM to organize long ASR meeting transcript.

Designed for ~/Downloads/meeting_transcript_0602/0602.txt but generic enough.
"""
import argparse, re, sys, json, textwrap
from pathlib import Path
from mlx_lm import load, generate


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def split_by_lines(text: str, max_chars: int = 9000):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    chunks, cur, n = [], [], 0
    for ln in lines:
        if cur and n + len(ln) + 1 > max_chars:
            chunks.append('\n'.join(cur))
            cur, n = [], 0
        cur.append(ln)
        n += len(ln) + 1
    if cur:
        chunks.append('\n'.join(cur))
    return chunks


def chat_prompt(tokenizer, system: str, user: str) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if hasattr(tokenizer, 'apply_chat_template'):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return f"系统：{system}\n\n用户：{user}\n\n助手："


def clean(out: str) -> str:
    out = out.strip()
    # Remove common accidental template tails.
    out = re.sub(r"<\|im_end\|>.*$", "", out, flags=re.S).strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('--model', default='mlx-community/Qwen2.5-3B-Instruct-4bit')
    ap.add_argument('--max-chars', type=int, default=8500)
    ap.add_argument('--max-tokens-chunk', type=int, default=1100)
    ap.add_argument('--max-tokens-final', type=int, default=1800)
    args = ap.parse_args()

    src = Path(args.input).expanduser()
    outp = Path(args.output).expanduser()
    text = read_text(src)
    chunks = split_by_lines(text, args.max_chars)
    print(f"[local-llm] loading {args.model} ...", file=sys.stderr, flush=True)
    model, tokenizer = load(args.model)

    system = (
        "你是严谨的中文会议纪要秘书。任务是整理ASR转写稿。"
        "必须保留事实、时间、单位、事项和责任要求；不要编造；"
        "ASR可能有错别字，请在不改变原意的情况下纠正常见同音错字；"
        "涉及不确定的人名地名数字，用【待核】标注；输出结构化Markdown。"
    )
    partials = []
    for i, ch in enumerate(chunks, 1):
        user = f"""以下是会议转写稿第 {i}/{len(chunks)} 段。请整理为“本段纪要”，要求：
1. 提炼本段议题/发言单位；
2. 按条列出关键事实、风险点、处置措施、工作要求；
3. 保留重要时间、数字、平台、地点；
4. 不要总结全文，只处理本段；
5. 输出Markdown，不要寒暄。

转写稿：
{ch}
"""
        prompt = chat_prompt(tokenizer, system, user)
        print(f"[local-llm] chunk {i}/{len(chunks)} chars={len(ch)}", file=sys.stderr, flush=True)
        ans = generate(model, tokenizer, prompt=prompt, max_tokens=args.max_tokens_chunk, verbose=False)
        ans = clean(ans)
        partials.append(f"## 分段整理 {i}\n\n{ans}\n")
        tmp = outp.with_suffix('.partial.md')
        tmp.write_text("\n".join(partials), encoding='utf-8')

    combined = "\n\n".join(partials)
    final_user = f"""下面是对同一场会议各段转写的本地模型分段整理。请合并为一份正式会议纪要，要求：

- 标题：0602会议录音本地模型整理纪要
- 包含：会议主题、主要议程、各单位/人员发言要点、重点风险研判、工作部署、责任清单/待办事项、需复核信息。
- 去重合并同类事项，按逻辑重排。
- 保留关键时间节点，例如6月3日8时至6月6日8时等。
- 不要编造未出现的信息；不确定信息标【待核】。
- 输出Markdown。

分段整理如下：
{combined}
"""
    print("[local-llm] final merge", file=sys.stderr, flush=True)
    final_prompt = chat_prompt(tokenizer, system, final_user)
    final = clean(generate(model, tokenizer, prompt=final_prompt, max_tokens=args.max_tokens_final, verbose=False))

    header = f"""# 0602会议录音本地模型整理纪要

> 整理方式：本机 Apple Silicon + MLX + `{args.model}` 分块整理后合并。  
> 原始转写：`{src}`  
> 提醒：ASR转写存在同音字/专名误识别，正式材料请对照录音复核。

"""
    outp.write_text(header + final.strip() + "\n\n---\n\n# 附：分段整理草稿\n\n" + combined, encoding='utf-8')
    print(f"[local-llm] wrote {outp}", file=sys.stderr)


if __name__ == '__main__':
    main()
