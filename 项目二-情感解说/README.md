# 项目二 · 情感解说

给一段故事，按约束文档生成激情洋溢的解说词，再用 **IndexTTS-2.5 情感声音模型**（B站开源）带情感朗读。
情绪可调：激情洋溢 / 兴奋 / 愤怒 / 惊喜 / 低落 / 平静，可跟随解说词逐段情感标注，也可整段统一。

**启动方式只有一个：双击 `启动.bat`**，浏览器自动打开 `http://127.0.0.1:9620`。

## 使用步骤

1. 双击 `启动.bat`（首次运行如引擎加载失败，先双击 `修复wetext.bat` 修复引擎依赖，可重复执行）；
2. 打开 `config.yaml`，在 `deepseek.api_key` 填入你的 DeepSeek Key
   （[platform.deepseek.com](https://platform.deepseek.com) 申请；不填则回退本地 Ollama，保存后立即生效、无需重启）；
3. 页面左侧输入故事 → 「生成激情解说词」→ 右侧选情绪模式/强度 → 点「朗读」→ 播放/下载音频。

产物保存在 `解说音频\`。

## 目录说明

```
启动.bat / 关闭.bat        启动（自动处理端口占用、崩溃自动重启）/ 一键停止
server.py                 后端服务：页面 / 解说词 / 合成任务 / 引擎管理
deepseek_client.py        约束文档 + 故事 → DeepSeek → 解说词 JSON
engines.py                语音引擎按需启停（IndexTTS-2.5）
fix_wetext.py             引擎依赖修复脚本（修复wetext.bat 调用它）
约束文档.md                发给 DeepSeek 的输出格式约束（页面里可直接改）
config.yaml               本机配置（DeepSeek Key、情绪预设等；模板 config.example.yaml）
static\index.html         前端页面
model_cache\              HF/ModelScope 模型缓存（不占 C 盘）
解说音频\                 生成的音频
index-tts\                语音引擎 IndexTTS-2.5（tts_server.py 为自研封装；.venv 为运行环境）
测试\                     测试截图、音频/视频产物与测试报告
```

## 常见问题

- **点朗读后要等多久**：第一次点朗读会自动启动语音引擎并加载模型（本机 USB 盘实测约 15 分钟，
  页面会显示"引擎加载中"进度）；之后再点就是秒级响应。
- **引擎加载失败 / 一直启动中**：双击 `修复wetext.bat`。wetext 包在 Windows + 中文路径下会让
  IndexTTS 引擎加载必败，脚本会装齐依赖、补全包数据并打补丁，可重复执行。
- **生成解说词报错提示配置 DeepSeek**：把 Key 填进 `config.yaml` 保存后重试即可，无需重启。
- **换情绪预设**：在 `config.yaml` 的 `tts.index_tts.presets` 里加减情绪预设。
- **显存**：RTX 4080 16GB 够用。

接口文档见 `接口文档.md`，测试记录见 `测试\测试报告.md`。
