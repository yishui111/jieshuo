# 项目一 · 专属声音

把你的激情解说录音训练成**专属声音模型**（GPT-SoVITS），再用它朗读任意故事生成的激情解说词。
还没训练时也能用：自动退回「默认参考音色」零样本克隆朗读。

**启动方式只有一个：双击 `启动.bat`**，浏览器自动打开 `http://127.0.0.1:9610`。

## 使用步骤

1. 双击 `启动.bat`；
2. 打开 `config.yaml`，在 `deepseek.api_key` 填入你的 DeepSeek Key
   （[platform.deepseek.com](https://platform.deepseek.com) 申请；不填则回退本地 Ollama，保存后立即生效、无需重启）；
3. 页面左侧输入故事 → 「生成激情解说词」→ 右侧点「用专属声音朗读」→ 播放/下载音频；
4. 声音训练：把激情解说录音放进 `训练素材\`（3~30 分钟，无 BGM），页面「开始训练」全自动完成：
   切片 → 语音识别标注 → 数据预处理 → SoVITS 微调 → GPT 微调，训练完自动启用。

产物保存在 `解说音频\`。

## 目录说明

```
启动.bat / 关闭.bat        启动（自动处理端口占用、崩溃自动重启）/ 一键停止
server.py                 后端服务：页面 / 解说词 / 合成任务 / 训练任务 / 引擎管理
train_voice.py            声音训练编排（调用 GPT-SoVITS 的训练脚本）
deepseek_client.py        约束文档 + 故事 → DeepSeek → 解说词 JSON
engines.py                语音引擎按需启停（GPT-SoVITS）
约束文档.md                发给 DeepSeek 的输出格式约束（页面里可直接改）
config.yaml               本机配置（DeepSeek Key 等；模板 config.example.yaml）
static\index.html         前端页面
训练素材\                 ★ 把你的解说录音放这里
训练数据\                 训练中间数据（切片、标注）
model_cache\              HF/ModelScope 模型缓存（不占 C 盘）
解说音频\                 生成的音频
GPT-SoVITS\               语音引擎（api_server.py 为自研封装；.venv 为运行环境）
测试\                     测试截图、音频产物与测试报告
```

## 常见问题

- **点朗读后要等多久**：第一次点朗读会自动启动 GPT-SoVITS 引擎并加载模型（约 1~2 分钟），
  之后再点就是秒级响应。
- **生成解说词报错提示配置 DeepSeek**：把 Key 填进 `config.yaml` 保存后重试即可，无需重启。
- **训练报素材为空**：录音还没放进 `训练素材\`，或格式不在 mp3/wav/flac/m4a/ogg 里。
- **显存**：RTX 4080 16GB 够用；训练时不要同时合成。
- **换音色**：换录音重新训练，或在页面「训练产物」里切换历史声音。

接口文档见 `接口文档.md`，测试记录见 `测试\测试报告.md`。
