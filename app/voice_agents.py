from agents import Agent
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from agents.voice import (
    SingleAgentVoiceWorkflow,
    VoicePipeline,
)


# Создаем русскоязычного агента
russian_agent = Agent(
    name="Russian",
    handoff_description="Русскоговорящий агент.",
    instructions=prompt_with_handoff_instructions(
        "Ты общаешься с человеком, будь вежливым и лаконичным. Говори на русском языке.",
    ),
    model="gpt-4o-mini",
)

# Основной агент
main_agent = Agent(
    name="Assistant",
    instructions=prompt_with_handoff_instructions(
        "Если пользователь говорит на русском, передай общение русскоязычному агенту.",
    ),
    model="gpt-4o-mini",
    handoffs=[russian_agent],
)


# Создаем голосовой конвейер
def create_voice_pipeline():
    return VoicePipeline(workflow=SingleAgentVoiceWorkflow(main_agent))
