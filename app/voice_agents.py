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
    async def run(self, text: str) -> AsyncIterator[str]:
        # Выводим транскрибированный текст
        print(f"Транскрибированный текст: {text}")

        # Используем стандартный процесс обработки
        async for response in super().run(text):
            print(f"Ответ: {response}")
            yield response


def read_instructions(index):
    instructions_path = Path(__file__).parent.parent / "instructions.txt"
    with open(instructions_path, "r", encoding="utf-8") as f:
        instructions = f.readlines()
    return prompt_with_handoff_instructions(instructions[index].strip())


client_agent = Agent(
    name="Client",
    handoff_description="клиент",
    instructions=read_instructions(0),
    model="gpt-4o-mini",
    model_settings=ModelSettings(max_tokens=100),
)

main_agent = Agent(
    name="Assistant",
    instructions=prompt_with_handoff_instructions(
        "Всегда отвечай на русском языке, Если пользователь говорит (чем могу помочь) передай управление клиенту"
    ),
    model="gpt-4o-mini",
    handoffs=[client_agent],
    model_settings=ModelSettings(max_tokens=100),
)


def create_voice_pipeline(language="ru"):
    """
    Создает голосовой конвейер с настройками для конкретного языка.

    Args:
        language (str): Код языка

    Returns:
        VoicePipeline: Настроенный голосовой конвейер
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
