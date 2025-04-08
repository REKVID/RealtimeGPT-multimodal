from agents.voice import TTSModelSettings

# Настройки для русскоязычного TTS
RUSSIAN_TTS_SETTINGS = TTSModelSettings(
    voice="alloy",  # Используем стабильный голос alloy
    speed=1.5,  # Нормальная скорость речи
    instructions="""
    Voice: Clear and professional, maintaining consistent pace and tone
    Pronunciation: Precise and natural Russian pronunciation
    Speed: Maintain steady, moderate pace throughout the response
    Tone: Warm and engaging, but professional
    Emotion: Maintain consistent level of engagement
    Pauses: Natural breaks between sentences, no dramatic pauses
    Volume: Consistent throughout the response
    """,
)
