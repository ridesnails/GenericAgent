---
skill: scheduled_task
domain: system
version: "1.0"
tags: [schedule, cron, task, automation]
cc_quick: "定时任务系统 — JSON定义/自动执行/历史报告管理"
cc_keywords: ["定时任务", "schedule", "自动执行", "任务调度"]
---
# 定时任务 SOP

目录：`../sche_tasks/` 放任务定义JSON，`../sche_tasks/done/` 放执行报告

## 任务JSON格式（*.json）
```json
{"schedule":"08:00", "repeat":"daily", "enabled":true, "prompt":"...", "max_delay_hours":6, "llm":"claude"}
```
repeat可选：daily | weekday | weekly | monthly | once | every_Nh（每N小时）| every_Nd（每N天）
max_delay_hours（可选，默认6）：超过schedule多少小时后不再触发，防止开机太晚执行过时任务
llm（可选）：本任务指定模型，按名字模糊匹配（如 gpt/claude/deepseek/glm）。scheduler在prompt首行注入 `[LLM] <name>`，agentmain的reflect循环解析后 next_llm 切换该模型执行，任务完成后自动恢复默认 llm_no=0（gpt）。匹配不到则回退默认模型。不填=用默认模型。

## 触发流程
1. scheduler.py（reflect/）每60秒轮询 sche_tasks/*.json
2. 条件全满足才触发：enabled=true + 当前时间≥schedule + 冷却时间已过（基于done/最新报告时间戳）
3. 触发时拼prompt，含报告路径 `../sche_tasks/done/YYYY-MM-DD_任务名.md`
4. **收到任务后第一件事**：用 update_working_checkpoint 记录报告目标文件路径，防止长任务执行中遗忘
5. 执行完毕后将报告写入上述路径（scheduler靠此文件判断今天已执行）

## 日志与监控
- scheduler自动写日志到 `sche_tasks/scheduler.log`（触发/跳过/错误）
- `scheduler.health_check()` 返回所有任务状态列表（HEALTHY/OVERDUE/DISABLED/NEVER_RUN/ERROR）
- JSON解析错误、schedule格式错误、未知repeat类型均会记录日志

## 运行守护
- macOS由LaunchAgent `~/Library/LaunchAgents/com.qing.genericagent.scheduler.plist` 托管，命令应使用项目venv的python运行 `agentmain.py --reflect reflect/scheduler.py`；避免退回系统`/usr/bin/python3`导致依赖/SSL告警。
- scheduler.py用本机TCP端口`45762`做单实例锁；若launchd启动后无轮询日志，先查 `lsof -nP -iTCP:45762 -sTCP:LISTEN`，避免旧bash循环/旧python占锁导致launchd进程空转。
- 修改agentmain.py或reflect/scheduler.py后，需 `launchctl kickstart -k gui/$(id -u)/com.qing.genericagent.scheduler` 重启服务加载新代码，再确认端口45762 LISTEN。

## 注意
- once类型：执行一次后冷却100年（实际效果为永久跳过）
- 任务文件只管"干什么"，报告路径由scheduler自动生成注入prompt
- sche_tasks目录在../，即code root下