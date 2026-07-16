"""语音转文字 — 通过 OpenAI Whisper API 将德语音频转为德语文本"""

import io
import queue
import threading
import logging

import numpy as np
import soundfile as sf
from openai import OpenAI

import config

logger = logging.getLogger(__name__)


class SpeechToText:
    """将音频句子片段通过 Whisper API 转写为德语文本"""

    def __init__(self, sentence_queue: queue.Queue, text_queue: queue.Queue):
        """
        Args:
            sentence_queue: 来自 VAD 的完整句子音频（numpy array）
            text_queue: 输出德语文本字符串
        """
        self._sentence_queue = sentence_queue
        self._text_queue = text_queue
        self._running = False
        self._thread: threading.Thread | None = None
        self._client: OpenAI | None = None

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        if not config.OPENAI_API_KEY:
            logger.warning(
                "⚠️ 未设置 OPENAI_API_KEY！STT 无法工作。\n"
                "请在 config.py 中填入你的 OpenAI API Key。"
            )
            # 仍然启动，但收到音频时跳过处理
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)
        self._running = True
        self._thread = threading.Thread(target=self._transcribe_loop, daemon=True)
        self._thread.start()
        logger.info("STT 线程已启动")

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    # ------------------------------------------------------------------
    # 核心逻辑
    # ------------------------------------------------------------------

    def _transcribe_loop(self):
        while self._running:
            try:
                sentence_audio = self._sentence_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not config.OPENAI_API_KEY:
                # API Key 未配置，放入占位文本
                placeholder = "[请配置 OPENAI_API_KEY]"
                logger.warning(placeholder)
                self._text_queue.put(placeholder)
                continue

            try:
                text = self._transcribe(sentence_audio)
                if text.strip():
                    logger.info(f"📝 STT 结果: {text}")
                    self._text_queue.put(text)
                else:
                    logger.debug("STT 返回空文本，跳过")
            except Exception as e:
                logger.error(f"STT 请求失败: {e}")
                self._text_queue.put(f"[STT错误] {e}")

    def _transcribe(self, audio: np.ndarray) -> str:
        """调用 OpenAI Whisper API 转写音频"""
        # 确保 float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # 确保是 1D
        if audio.ndim == 2:
            audio = audio.flatten()

        # 写入内存 WAV 文件
        wav_buffer = io.BytesIO()
        sf.write(wav_buffer, audio, config.SAMPLE_RATE, format="WAV")
        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav"

        # 调用 Whisper API
        transcript = self._client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=wav_buffer,
            language=config.SOURCE_LANGUAGE,
            response_format="text",
        )

        return transcript.strip()
