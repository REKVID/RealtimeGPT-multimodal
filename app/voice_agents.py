from agents import Agent
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from agents.voice import (
    SingleAgentVoiceWorkflow,
    VoicePipeline,
    VoiceStreamEventAudio,
    VoiceStreamEventLifecycle,
    VoicePipelineConfig,
)
from pathlib import Path
from typing import AsyncIterator


class ExtendedVoiceWorkflow(SingleAgentVoiceWorkflow):
    async def run(self, text: str) -> AsyncIterator[str]:
        # Выводим транскрибированный текст от пользователя
        print(f"\nВходящий текст: {text}")

        # Накапливаем текст для отладки
        current_response = ""

        # Используем стандартный процесс обработки
        async for response in super().run(text):
            # Добавляем часть ответа к полному тексту
            current_response += response
            print(f"Часть ответа модели: {response}")

            # Немедленно отправляем каждую часть на синтез речи
            yield response


def read_instructions(index):
    instructions_path = Path(__file__).parent / "instructions.txt"
    with open(instructions_path, "r", encoding="utf-8") as f:
        instructions = f.readlines()
    return prompt_with_handoff_instructions(instructions[index].strip())


# Создаем агента для клиента
client_agent = Agent(
    name="Client",
    handoff_description="клиент",
    instructions=read_instructions(0),
    model="gpt-4o-mini",
)

# Основной агент
main_agent = Agent(
    name="Assistant",
    instructions="Всегда отвечай на русском языке, Если пользователь говорит (чем могу помочь) передай управление клиенту",
    model="gpt-4o-mini",
    handoffs=[client_agent],
)


# Создаем голосовой конвейер
def create_voice_pipeline():
    return VoicePipeline(workflow=ExtendedVoiceWorkflow(main_agent))
