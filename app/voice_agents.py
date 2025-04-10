from agents import Agent, ModelSettings
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from agents.voice import (
    SingleAgentVoiceWorkflow,
    VoicePipeline,
    VoicePipelineConfig,
)
from pathlib import Path
from typing import AsyncIterator  # НЕ ВЫЕБАВАТЬСЯ так надо
from .tts_settings import RUSSIAN_TTS_SETTINGS


class ExtendedVoiceWorkflow(SingleAgentVoiceWorkflow):
    """Расширенный рабочий процесс для обработки голосовых команд.

    Этот класс расширяет стандартный SingleAgentVoiceWorkflow для добавления
    дополнительной функциональности, такой как логирование транскрибированного
    текста и ответов.

    Args:
        text (str): Транскрибированный текст для обработки.

    Yields:
        str: Сгенерированные ответы от агента.
    """

    async def run(self, text: str) -> AsyncIterator[str]:
        # Выводим транскрибированный текст
        print(f"Транскрибированный текст: {text}")

        # Используем стандартный процесс обработки
        async for response in super().run(text):
            print(f"Ответ: {response}")
            yield response


def read_instructions():
    """Читает инструкции из файла.

    Returns:
        str: Полный текст инструкций с применением handoff_instructions.
    """
    instructions_path = Path(__file__).parent.parent / "instructions.txt"
    with open(instructions_path, "r", encoding="utf-8") as f:
        instructions = f.read()
    return prompt_with_handoff_instructions(instructions)


client_agent = Agent(
    name="Клиент",
    handoff_description="клиент",
    instructions=read_instructions(),
    model="gpt-4o",
    model_settings=ModelSettings(max_tokens=1000),
)

main_agent = Agent(
    name="Assistant",
    instructions=prompt_with_handoff_instructions(
        "Всегда отвечай на русском языке, Если пользователь говорит (чем могу помочь) передай управление клиенту"
    ),
    model="gpt-4o",
    handoffs=[client_agent],
    model_settings=ModelSettings(max_tokens=1000),
)


def create_voice_pipeline(language="ru"):
    """Создает настроенный голосовой конвейер для обработки аудио.

    Args:
        language (str, optional): Код языка для настройки STT и TTS моделей.
            По умолчанию "ru".

    Returns:
        VoicePipeline: Настроенный голосовой конвейер с указанным языком
            и соответствующими настройками TTS.

    Raises:
        Exception: Если не удалось установить язык для STT модели.

    Example:
        >>> pipeline = create_voice_pipeline("ru")
        >>> result = await pipeline.run(audio_input)
    """

    # Создаем конфигурацию с настройками TTS
    config = VoicePipelineConfig(tts_settings=RUSSIAN_TTS_SETTINGS)

    # Создаем конвейер с настроенной конфигурацией
    pipeline = VoicePipeline(workflow=ExtendedVoiceWorkflow(main_agent), config=config)

    # Явно устанавливаем язык для модели Whisper, если поддерживается
    try:
        if hasattr(pipeline.stt_model, "set_language"):
            pipeline.stt_model.set_language("ru")
        # В случае с OpenAI Whisper модель языку нужно задать напрямую
        elif hasattr(pipeline.stt_model, "language"):
            pipeline.stt_model.language = "ru"

        print(f"Установлен язык транскрипции: {'ru'}")
        print("Настройки TTS применены:", RUSSIAN_TTS_SETTINGS)
    except Exception as e:
        print(f"Не удалось установить язык для STT модели: {e}")

    return pipeline
