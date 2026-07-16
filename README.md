# 🎙️ InterviewBridge

> **智能模拟面试助手 — 帮你快速建立回答思路，支持任意语言。**

面试时脑子空白？InterviewBridge 实时监听会议音频，自动识别面试官的问题，并在屏幕悬浮窗中给出 **3~5 条口语化回答建议**，条条附带你的母语解释。翻译功能可一键开关，支持任意语言组合。

---

## 📸 效果预览

```
┌─────────────────────────────────────────┐
│  InterviewBridge [翻译模式]              │
│  ─────────────────────────────────────  │
│                                         │
│  #3  14:32:05                           │
│                                         │
│  🎤 面试官: Was sind Ihre Staerken?      │
│                                         │
│  📖 翻译: 你的优势是什么？               │
│                                         │
│  💬 回答思路:                            │
│    1. Ich bin sehr teamfaehig.           │
│       我很有团队协作能力                  │
│    2. Ich habe fuenf Jahre Erfahrung.    │
│       我有五年经验                       │
│    3. Ich arbeite gut unter Druck.       │
│       我能在压力下很好地工作              │
└─────────────────────────────────────────┘
```

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/longxunzhang1015/interview-bridge.git
cd interview-bridge

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置
cp config.example.py config.py
# 编辑 config.py：填入 OpenAI API Key，选择语言

# 4. (可选) 准备面试语料库
# 编辑 corpus.txt，写入你的背景、经历、常见问题和回答

# 5. 启动
python main.py
```

打开 Zoom / Teams / Meet → 开始面试 → 悬浮窗自动显示回答思路。

## ⚙️ 配置说明

在 `config.py` 中修改以下设置：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key | `"sk-..."` |
| `SOURCE_LANGUAGE` | 面试官语言 | `"de"` `"en"` `"ja"` `"fr"` |
| `TARGET_LANGUAGE` | 你的母语 | `"zh"` `"en"` `"ko"` |
| `ENABLE_TRANSLATION` | 翻译开关 | `True` 翻译模式 / `False` 纯思路模式 |

### 语言场景速查

| 场景 | SOURCE | TARGET | TRANSLATION |
|------|--------|--------|:-----------:|
| 🇩🇪 德国留学/求职 | `de` | `zh` | ON |
| 🇯🇵 日本留学/求职 | `ja` | `zh` | ON |
| 🇺🇸 英文面试 | `en` | `zh` | ON |
| 🇬🇧 英文模拟训练 | `en` | `en` | OFF |
| 🇫🇷 法语面试 | `fr` | `zh` | ON |

## 🧠 工作原理

```
系统音频 (WASAPI Loopback)
        │
        ▼
  智能 VAD 语音检测 (自适应能量阈值 + 防抖)
        │
        ▼
  Whisper API 语音转文字
        │
        ▼
  GPT-4o 理解问题 + 生成回答思路 (+ 可选翻译)
        │
        ▼
  tkinter 悬浮窗 (置顶显示 · 滚动历史)
```

## 📁 项目结构

```
interview-bridge/
├── main.py              # 入口
├── config.example.py    # 配置模板（复制为 config.py）
├── corpus.txt           # 面试语料库（你的准备材料）
├── audio_capture.py     # WASAPI Loopback 音频捕获
├── vad_detector.py      # 能量 VAD 语音检测
├── speech_to_text.py    # Whisper STT
├── llm_processor.py     # GPT-4o 回答生成 + 翻译
├── overlay_ui.py        # 悬浮窗 UI
├── requirements.txt     # Python 依赖
└── .gitignore
```

## 🔧 依赖

- Python 3.10+
- Windows 10/11（WASAPI loopback 需 Windows）
- OpenAI API Key

```bash
pip install numpy openai soundfile comtypes
```

## ❓ 常见问题

**Q: 支持 Mac/Linux 吗？**
A: 音频捕获模块目前基于 Windows WASAPI。Mac/Linux 支持计划中。

**Q: 一场面试花多少钱？**
A: OpenAI API 按量计费。1 小时面试约 $0.30~$0.50（Whisper + GPT-4o），约合 ¥2~4。

**Q: 需要装虚拟声卡吗？**
A: 不需要。InterviewBridge 直接通过 Windows 原生 WASAPI API 捕获系统音频。

**Q: 可以不用翻译功能吗？**
A: 可以。在 config.py 设置 `ENABLE_TRANSLATION = False`，进入纯思路模式（适合同语言面试训练）。

## 📄 许可

MIT License

---

**Made with ❤️ for interviewees worldwide.**
