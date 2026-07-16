"""面试 AI 助手 — 配置文件模板
使用前请将此文件重命名为 config.py 并填入你的 OpenAI API Key。
"""

# ===== 必填 =====
OPENAI_API_KEY = ""  # 在此填入你的 OpenAI API Key（Whisper + GPT-4o 共用）

# ===== 语言设置 =====
SOURCE_LANGUAGE = "de"   # 面试官说的语言（ISO 639-1 代码，如 en/ja/fr/ko）
TARGET_LANGUAGE = "zh"   # 你的母语（界面显示的语言）

# ===== 功能开关 =====
ENABLE_TRANSLATION = True   # True = 翻译+回答  False = 纯回答思路模式

# ===== 音频设置 =====
SAMPLE_RATE = 16000      # 采样率 16kHz（Whisper 推荐）
BLOCK_SIZE = 800         # 每块样本数（50ms @ 16kHz）
CHANNELS = 1             # 单声道

# ===== VAD 语音检测设置（能量检测） =====
ENERGY_THRESHOLD = 0.0015       # RMS 能量阈值（调小→更敏感）
SILENCE_DURATION_SEC = 1.5      # 连续静音多久（秒）后切分句子
MIN_SPEECH_DURATION_SEC = 0.4   # 最短语音时长（秒），短于此视为噪音
MAX_SPEECH_DURATION_SEC = 30.0  # 最长语音时长（秒），超出强制切分

# ===== STT 设置 =====
WHISPER_MODEL = "whisper-1"  # OpenAI Whisper 模型

# ===== LLM 设置 =====
GPT_MODEL = "gpt-4o"         # 翻译+回答生成用的模型
# 备选: "gpt-4o-mini"（更快更便宜）, "gpt-4o"（质量最高）

# ===== UI 设置 =====
WINDOW_WIDTH = 520
WINDOW_HEIGHT = 450
WINDOW_OPACITY = 0.85        # 窗口不透明度
FONT_SIZE_TRANSLATION = 11
FONT_SIZE_ANSWER = 10

# ===== 调试设置 =====
DEBUG = False

# ===== 面试语料库 =====
CORPUS_FILE = "corpus.txt"  # 语料库文件名（留空则不用）
