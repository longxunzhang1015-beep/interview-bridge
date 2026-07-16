"""LLM 处理模块 — OpenAI GPT-4o 提供回答思路和可选翻译"""

import json
import os
import queue
import threading
import logging

from openai import OpenAI

import config

logger = logging.getLogger(__name__)

# ---- 翻译模式 ON ----
BASE_PROMPT_WITH_TRANSLATION = """你是一个实时模拟面试 AI 助手，面试官用{src}提问。你的任务是帮助用户快速建立回答思路。

1. 用{target}准确解释面试官问了什么
2. 提供 3~5 条口语化{src}回答建议，每条下面紧跟{target}翻译

**回答风格（非常重要）：**
- 口语化、自然、像正常人说话，不要书面语
- 尽量用简单主句，避免复杂从句嵌套
- 每句 10~20 词，方便直接念出来
- 优先参考用户准备的语料库中的措辞和经历

严格按此 JSON 格式回复：
{{
  "question_explanation": "用{target}解释问题",
  "answer_lines": [
    {{"response": "第1句回答({src})", "meaning": "这句话的意思({target})"}},
    {{"response": "第2句回答({src})", "meaning": "这句话的意思({target})"}}
  ]
}}

注意：寒暄给 1-2 条即可，正式问题给 3-5 条，每条不超过 25 词。"""

# ---- 翻译模式 OFF (同语言模式) ----
BASE_PROMPT_NO_TRANSLATION = """你是一个实时模拟面试 AI 助手，面试官用{src}提问。你的任务是帮助用户快速建立回答思路。

1. 用{src}简要复述对方的提问要点
2. 提供 3~5 条口语化{src}回答建议，给出不同角度的思路

**回答风格（非常重要）：**
- 口语化、自然、像正常人说话，不要书面语
- 尽量用简单主句，避免复杂从句嵌套
- 每句 10~20 词，方便直接念出来
- 优先参考用户准备的语料库中的措辞和经历

严格按此 JSON 格式回复：
{{
  "question_summary": "用{src}简要复述问题",
  "answer_lines": [
    {{"response": "第1句回答", "note": "这条回答的思路/角度"}},
    {{"response": "第2句回答", "note": "这条回答的思路/角度"}}
  ]
}}

注意：寒暄给 1-2 条即可，正式问题给 3-5 条，每条不超过 25 词。"""


def _build_system_prompt() -> str:
    """构建完整系统提示（注入语料库上下文）"""

    # 选择基础模板
    if config.ENABLE_TRANSLATION:
        base = BASE_PROMPT_WITH_TRANSLATION.format(
            src=config.SOURCE_LANGUAGE,
            target=config.TARGET_LANGUAGE,
        )
    else:
        base = BASE_PROMPT_NO_TRANSLATION.format(
            src=config.SOURCE_LANGUAGE,
        )

    prompt = base

    # 尝试读取语料库
    corpus_path = None
    if config.CORPUS_FILE:
        config_dir = os.path.dirname(os.path.abspath(config.__file__))
        corpus_path = os.path.join(config_dir, config.CORPUS_FILE)

    if corpus_path and os.path.isfile(corpus_path):
        try:
            with open(corpus_path, "r", encoding="utf-8") as f:
                corpus = f.read().strip()

            lines = corpus.split("\n")
            effective = [
                line for line in lines
                if not line.strip().startswith("#") and line.strip()
            ]

            if effective:
                effective_corpus = "\n".join(effective)
                prompt += (
                    f"\n\n===== 用户准备的面试语料库 =====\n"
                    f"{effective_corpus}\n"
                    f"================================\n"
                    f"请根据以上语料库内容个性化回答建议，贴合用户背景。"
                )
                logger.info(f"语料库已加载 ({len(effective)} 行)")
            else:
                logger.info("语料库为空")

        except Exception as e:
            logger.warning(f"读取语料库失败: {e}")
    else:
        if config.CORPUS_FILE:
            logger.info(f"未找到语料库文件: {corpus_path}")

    return prompt


class LLMProcessor:
    """处理面试提问：理解问题 → 生成回答思路 + 可选翻译"""

    def __init__(self, text_queue: queue.Queue):
        self._text_queue = text_queue
        self._running = False
        self._thread: threading.Thread | None = None
        self._client: OpenAI | None = None
        self._on_result: callable | None = None
        self._system_prompt = _build_system_prompt()

    def set_callback(self, callback: callable):
        """回调参数: (explanation: str, answer_lines: list[dict], original_text: str)
        answer_lines 格式: [{"response": "...", "extra": "..."}, ...]"""
        self._on_result = callback

    def start(self):
        if self._running:
            return
        if not config.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY 未设置！")
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        mode = "翻译模式" if config.ENABLE_TRANSLATION else "同语言模式"
        logger.info(f"LLM 已启动 ({mode}: {config.SOURCE_LANGUAGE} -> {config.TARGET_LANGUAGE})")

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _process_loop(self):
        while self._running:
            try:
                text = self._text_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not config.OPENAI_API_KEY:
                self._update_ui(
                    "[请配置 API Key]",
                    [{"response": "Bitte API-Key konfigurieren.", "extra": "请配置"}],
                    text,
                )
                continue

            try:
                explanation, answer_lines = self._call_gpt(text)
                logger.info(f"问题理解: {explanation}")
                for i, line in enumerate(answer_lines):
                    logger.info(f"  回答{i+1}: {line['response']}")
                self._update_ui(explanation, answer_lines, text)
            except Exception as e:
                logger.error(f"LLM 请求失败: {e}")
                self._update_ui(
                    f"[错误] {e}",
                    [{"response": f"[Fehler] {e}", "extra": str(e)}],
                    text,
                )

    def _call_gpt(self, text: str) -> tuple[str, list[dict]]:
        """调用 GPT-4o"""
        response = self._client.chat.completions.create(
            model=config.GPT_MODEL,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=800,
        )

        content = response.choices[0].message.content.strip()
        result = json.loads(content)

        # 翻译模式 vs 非翻译模式 → 统一字段
        if config.ENABLE_TRANSLATION:
            explanation = result.get("question_explanation", "")
            raw_lines = result.get("answer_lines", [])
            # 映射 response/meaning 到统一格式
            answer_lines = [
                {"response": item.get("response", ""), "extra": item.get("meaning", "")}
                for item in raw_lines
            ]
        else:
            explanation = result.get("question_summary", "")
            raw_lines = result.get("answer_lines", [])
            answer_lines = [
                {"response": item.get("response", ""), "extra": item.get("note", "")}
                for item in raw_lines
            ]

        # 向后兼容旧格式
        if not answer_lines:
            if "answer_hint" in result:
                answer_lines = [{"response": result["answer_hint"], "extra": ""}]

        if not answer_lines:
            answer_lines = [{"response": "(无法生成回答)", "extra": ""}]

        return explanation, answer_lines

    def _update_ui(self, explanation: str, answer_lines: list[dict], original_text: str):
        if self._on_result:
            self._on_result(explanation, answer_lines, original_text)
