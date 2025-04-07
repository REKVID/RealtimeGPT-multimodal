from agents import Agent
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from agents.voice import (
    SingleAgentVoiceWorkflow,
    VoicePipeline,
)
from pathlib import Path
from typing import AsyncIterator


class ExtendedVoiceWorkflow(SingleAgentVoiceWorkflow):
    async def run(self, text: str) -> AsyncIterator[str]:
        # Выводим транскрибированный текст
        print(f"Транскрибированный текст: {text}")

        # Используем стандартный процесс обработки
        async for response in super().run(text):
            yield response


def read_instructions(index):
    instructions_path = Path(__file__).parent / "instructions.txt"
    with open(instructions_path, "r", encoding="utf-8") as f:
        instructions = f.readlines()
    return prompt_with_handoff_instructions(instructions[index].strip())


# Создаем русскоязычного агента
client_agent = Agent(
    name="Russian",
    handoff_description="клиент",
    instructions=read_instructions(0),
    model="gpt-4o-mini",
)

# Основной агент
main_agent = Agent(
    name="Assistant",
    instructions=prompt_with_handoff_instructions(
        "Всегда отвечай на русском языке, Если пользователь говорит (чем могу помочь) передай управление клиенту"
    ),
    model="gpt-4o-mini",
    handoffs=[client_agent],
)


# Создаем голосовой конвейер
def create_voice_pipeline():
    return VoicePipeline(workflow=ExtendedVoiceWorkflow(main_agent))
