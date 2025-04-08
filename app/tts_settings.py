from agents.voice import TTSModelSettings

# Настройки рандом пока что
RUSSIAN_TTS_SETTINGS = TTSModelSettings(
    voice="alloy",
    speed=1.6,
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
