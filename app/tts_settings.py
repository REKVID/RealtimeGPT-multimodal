from agents.voice import TTSModelSettings

# Настройки рандом пока что
RUSSIAN_TTS_SETTINGS = TTSModelSettings(
    voice="alloy",
    speed=2,
    instructions="""
    Быстрая четкая, живая речь, заинтересованная, не слишком много слов, не слишком много пауз.
    """,
)
