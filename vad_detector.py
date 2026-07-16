"""语音活动检测 (VAD) — 基于能量检测语音段落并切分为句子

原理：计算音频信号的 RMS 能量，超过动态阈值视为语音。
带语音起始防抖和句中止顿容错，减少截断和误检。
"""

import queue
import threading
import logging

import numpy as np

import config

logger = logging.getLogger(__name__)


class VADDetector:
    """监听音频队列，检测语音段落，将完整句子输出到句子队列"""

    def __init__(self, audio_queue: queue.Queue, sentence_queue: queue.Queue):
        self._audio_queue = audio_queue
        self._sentence_queue = sentence_queue
        self._running = False
        self._thread: threading.Thread | None = None

        # 状态机
        self._buffer: list[np.ndarray] = []
        self._is_speaking = False
        self._silence_blocks = 0
        self._speech_blocks = 0

        # 能量阈值（从 config 读取）
        self._energy_threshold = config.ENERGY_THRESHOLD
        self._noise_floor = 0.0005            # 初始噪声基底
        self._noise_alpha = 0.02              # 噪声基底学习率（更慢=更稳定）

        # 计数阈值
        block_dur = config.BLOCK_SIZE / config.SAMPLE_RATE  # 50ms/block
        self._silence_limit = int(config.SILENCE_DURATION_SEC / block_dur)
        self._min_speech = int(config.MIN_SPEECH_DURATION_SEC / block_dur)
        self._max_speech = int(config.MAX_SPEECH_DURATION_SEC / block_dur)

        # 语音起始防抖：需要连续 N 帧语音才确认开始（过滤短促噪音）
        self._onset_counter = 0
        self._onset_required = 4   # 4 blocks = 200ms 连续语音才确认开始

        # 句中止顿容错：允许说话中间短暂停顿不切分
        # 只有静音超过 silence_limit 才真正切分；短于此的静音忽略
        # silence_limit 已经是 1.5s，足够覆盖大部分自然停顿

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"VAD 已启动 (阈值={self._energy_threshold:.4f}, "
            f"静音={config.SILENCE_DURATION_SEC}s, "
            f"起始防抖={self._onset_required * 50}ms, "
            f"最短={config.MIN_SPEECH_DURATION_SEC}s, "
            f"最长={config.MAX_SPEECH_DURATION_SEC}s)"
        )

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # 核心逻辑
    # ------------------------------------------------------------------

    def _detect_loop(self):
        while self._running:
            try:
                audio_chunk = self._audio_queue.get(timeout=0.3)
            except queue.Empty:
                continue

            # 计算 RMS 能量
            if audio_chunk.ndim == 2:
                audio_1d = audio_chunk.flatten()
            else:
                audio_1d = audio_chunk

            rms = float(np.sqrt(np.mean(audio_1d.astype(np.float64) ** 2)))

            # 自适应噪声基底（只在静音状态时学习）
            if not self._is_speaking and rms < self._energy_threshold:
                self._noise_floor = (
                    self._noise_alpha * rms
                    + (1 - self._noise_alpha) * self._noise_floor
                )

            # 动态阈值
            threshold = max(self._energy_threshold, self._noise_floor * 4.0)

            is_speech = rms > threshold

            if is_speech:
                self._handle_speech(audio_chunk)
            else:
                self._handle_silence(audio_chunk)

            if config.DEBUG and (is_speech or self._is_speaking):
                logger.debug(
                    f"RMS={rms:.5f} thr={threshold:.5f} "
                    f"nfloor={self._noise_floor:.5f} "
                    f"speech={is_speech} speaking={self._is_speaking} "
                    f"buf={len(self._buffer)} sil={self._silence_blocks}"
                )

        # 退出时输出剩余缓冲
        if self._is_speaking and len(self._buffer) >= self._min_speech:
            self._finish_sentence()

    # ------------------------------------------------------------------
    # 语音处理
    # ------------------------------------------------------------------

    def _handle_speech(self, audio_chunk: np.ndarray):
        if self._is_speaking:
            # 正在说话：追加到缓冲，重置静音计数
            self._buffer.append(audio_chunk)
            self._speech_blocks += 1
            self._silence_blocks = 0  # 中间短暂停顿不算

            # 强制切分：超过最长时长
            if self._speech_blocks >= self._max_speech:
                logger.info("⚠️ 达到最长语音时长，强制切分")
                self._finish_sentence()
        else:
            # 还没确认在说话：积累 onset 计数
            self._onset_counter += 1
            self._buffer.append(audio_chunk)

            if self._onset_counter >= self._onset_required:
                # 确认语音开始
                self._is_speaking = True
                self._speech_blocks = self._onset_counter
                self._silence_blocks = 0
                if config.DEBUG:
                    logger.debug("🔊 语音开始")
            # 否则继续积累（可能是噪音）

    # ------------------------------------------------------------------
    # 静音处理
    # ------------------------------------------------------------------

    def _handle_silence(self, audio_chunk: np.ndarray):
        if self._is_speaking:
            # 正在说话中遇到静音
            self._buffer.append(audio_chunk)
            self._silence_blocks += 1

            if self._silence_blocks >= self._silence_limit:
                # 静音持续够久 → 句子结束
                self._finish_sentence()
        else:
            # 还没确认在说话，且遇到静音 → 重置 onset
            if self._onset_counter > 0 and self._onset_counter < self._onset_required:
                # 语音不够长，丢弃（短促噪音）
                if config.DEBUG:
                    logger.debug(f"丢弃噪音 ({self._onset_counter} blocks)")
                self._buffer = []
                self._onset_counter = 0

    # ------------------------------------------------------------------
    # 句子完成
    # ------------------------------------------------------------------

    def _finish_sentence(self):
        """完成一个句子，将音频拼起来放入句子队列"""
        # 去掉末尾的静音帧（保留最后几帧让句子自然结束）
        trim_count = min(self._silence_blocks, 3)  # 最多保留 150ms 尾音
        effective_len = len(self._buffer) - trim_count

        if effective_len < self._min_speech:
            if config.DEBUG:
                logger.debug(f"丢弃过短片段 ({effective_len} < {self._min_speech} blocks)")
            self._reset()
            return

        # 拼接
        sentence_audio = np.concatenate(self._buffer[:effective_len], axis=0)
        duration = len(sentence_audio) / config.SAMPLE_RATE

        logger.info(
            f"📦 句子: {duration:.1f}s, "
            f"{len(sentence_audio)} samples @ {config.SAMPLE_RATE}Hz"
        )

        try:
            self._sentence_queue.put_nowait(sentence_audio)
        except queue.Full:
            logger.warning("句子队列已满，丢弃最旧的")
            try:
                self._sentence_queue.get_nowait()
                self._sentence_queue.put_nowait(sentence_audio)
            except queue.Empty:
                pass

        self._reset()

    def _reset(self):
        """重置状态"""
        self._buffer = []
        self._is_speaking = False
        self._speech_blocks = 0
        self._silence_blocks = 0
        self._onset_counter = 0
