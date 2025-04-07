from agents import Agent
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from agents.voice import SingleAgentVoiceWorkflow, VoicePipeline, VoiceWorkflowBase
from pathlib import Path
import asyncio


class CustomVoiceWorkflow(VoiceWorkflowBase):
    def __init__(self, agent):
        self.agent = agent

    async def run(self, text: str) -> str:
        # Выводим транскрибированный текст
        print(f"Транскрибированный текст: {text}")

        # Отправляем текст агенту
        result = await self.agent.complete(text)
        return result.response


def read_instructions(index):
    instructions_path = Path(__file__).parent / "instructions.txt"
    with open(instructions_path, "r", encoding="utf-8") as f:
        instructions = f.readlines()
    return prompt_with_handoff_instructions(instructions[index].strip())


# Создаем русскоязычного агента
russian_agent = Agent(
    name="Russian",
    handoff_description="Русскоговорящий агент.",
    instructions=read_instructions(0),
    model="gpt-4o-mini",
)

# Основной агент
main_agent = Agent(
    name="Assistant",
    instructions=read_instructions(0),
    model="gpt-4o-mini",
    # handoffs=[russian_agent],
)


# Создаем голосовой конвейер
def create_voice_pipeline():
    return VoicePipeline(workflow=CustomVoiceWorkflow(main_agent))
