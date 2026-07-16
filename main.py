#!/usr/bin/env python3
"""面试 AI 助手 — 实时德语翻译 + 回答提示

用法:
    python main.py

首次使用:
    1. 编辑 config.py，填入 OPENAI_API_KEY
    2. pip install -r requirements.txt
"""

import queue
import logging
import signal
import sys
import time

import config

from audio_capture import AudioCapture
from vad_detector import VADDetector
from speech_to_text import SpeechToText
from llm_processor import LLMProcessor
from overlay_ui import OverlayUI

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  🎙️  面试 AI 助手 - Interview Assistant")
    print("  实时德语翻译 + 回答提示")
    print("=" * 60)

    # ----- 检查配置 -----
    if not config.OPENAI_API_KEY:
        print()
        print("  ⚠️  未检测到 OPENAI_API_KEY！")
        print("  请编辑 config.py 填入你的 OpenAI API Key：")
        print(f"  文件位置: {__file__.replace('main.py', 'config.py')}")
        print()
        print("  程序将继续运行，但 STT 和翻译功能不会工作。")
        print("-" * 60)

    # ----- 创建队列 -----
    audio_queue = queue.Queue(maxsize=200)
    sentence_queue = queue.Queue(maxsize=50)
    text_queue = queue.Queue(maxsize=50)

    # ----- 创建模块 -----
    audio_capture = AudioCapture(audio_queue)
    vad = VADDetector(audio_queue, sentence_queue)
    stt = SpeechToText(sentence_queue, text_queue)
    llm = LLMProcessor(text_queue)
    ui = OverlayUI()

    # ----- 连接 LLM → UI -----
    llm.set_callback(lambda t, a, o: ui.update(t, a, o))

    # ----- 启动 -----
    print("\n启动模块...")

    try:
        # 1. 先启动 UI（它有自己的线程）
        logger.info("启动 UI...")
        ui.start_in_thread()
        time.sleep(0.5)

        # 2. 启动音频捕获
        logger.info("启动音频捕获...")
        audio_capture.start()

        # 3. 启动 VAD 检测
        logger.info("启动 VAD 检测...")
        vad.start()

        # 4. 启动 STT
        logger.info("启动 STT...")
        stt.start()

        # 5. 启动 LLM 处理
        logger.info("启动 LLM 处理...")
        llm.start()

        print()
        print("  ✅ 所有模块已启动！")
        print("  悬浮窗已显示在屏幕右侧 →")
        print("  按 Ctrl+C 退出")
        print("-" * 60)

        # ----- 优雅退出 -----
        # 在 Windows 上用 signal 不太好用，改用 KeyboardInterrupt
        while True:
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n正在退出...")
    except Exception as e:
        logger.error(f"运行异常: {e}", exc_info=True)
    finally:
        # ----- 停止所有模块 -----
        logger.info("停止 LLM...")
        llm.stop()
        logger.info("停止 STT...")
        stt.stop()
        logger.info("停止 VAD...")
        vad.stop()
        logger.info("停止音频捕获...")
        audio_capture.stop()
        logger.info("停止 UI...")
        ui.stop()

        print("已退出。")


if __name__ == "__main__":
    main()
