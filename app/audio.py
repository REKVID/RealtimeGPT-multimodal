"""
Модуль обработки аудио данных
"""

import io
import wave
import struct
import time
import logging
import numpy as np
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from fastapi import HTTPException

from .config import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH, MIN_AUDIO_LENGTH

# Настройка логирования
logger = logging.getLogger("voice_app")


def generate_wav_header(sample_rate, bits_per_sample, channels, n_samples):
    """Генерирует WAV-заголовок для аудио данных"""
    datasize = n_samples * channels * bits_per_sample // 8
    header = bytes("RIFF", "ascii")
    header += struct.pack("<L", 36 + datasize)
    header += bytes("WAVE", "ascii")
    header += bytes("fmt ", "ascii")
    header += struct.pack("<L", 16)
    header += struct.pack("<H", 1)  # PCM формат
    header += struct.pack("<H", channels)
    header += struct.pack("<L", sample_rate)
    header += struct.pack(
        "<L", sample_rate * channels * bits_per_sample // 8
    )  # байт/сек
    header += struct.pack("<H", channels * bits_per_sample // 8)  # блок выравнивания
    header += struct.pack("<H", bits_per_sample)
    header += bytes("data", "ascii")
    header += struct.pack("<L", datasize)
    return header


def process_audio_data(audio_data, connection_id=None, session=None):
    """Обрабатывает входные аудиоданные и возвращает нормализованные сэмплы"""
    debug_prefix = (
        f"debug/audio_{connection_id}_{session}"
        if connection_id and session
        else "debug/audio"
    )
    timestamp = int(time.time())

    try:
        # Сохраняем исходный формат аудио для диагностики
        with open(f"{debug_prefix}_raw_{timestamp}.bin", "wb") as f:
            f.write(audio_data)

        # Определяем тип файла по первым байтам
        file_type = ""
        if len(audio_data) > 10:
            if audio_data.startswith(b"RIFF"):
                file_type = "wav"
            elif audio_data.startswith(b"\xff\xfb") or audio_data.startswith(b"ID3"):
                file_type = "mp3"
            elif audio_data.startswith(b"OggS"):
                file_type = "ogg"
            elif audio_data.startswith(b"fLaC"):
                file_type = "flac"

        logger.info(
            f"Аудио формат определен как: {file_type or 'неизвестный'}, размер: {len(audio_data)} байт"
        )

        # Для аудиоданных без явного формата, добавляем WAV заголовок
        if not file_type and len(audio_data) > 44:
            # Предполагаем, что это сырые PCM данные
            logger.info("Принимаем данные как сырые PCM, добавляем WAV заголовок")

            # Проверяем, что данные могут быть PCM Int16
            try:
                # Преобразуем в numpy массив для проверки

                # Создаем временный WAV-файл
                with wave.open(
                    f"{debug_prefix}_with_header_{timestamp}.wav", "wb"
                ) as wav_file:
                    wav_file.setnchannels(CHANNELS)
                    wav_file.setsampwidth(SAMPLE_WIDTH)
                    wav_file.setframerate(SAMPLE_RATE)
                    wav_file.writeframes(audio_data)

                # Читаем как AudioSegment
                audio_segment = AudioSegment.from_file(
                    f"{debug_prefix}_with_header_{timestamp}.wav", format="wav"
                )
            except Exception as e:
                logger.error(f"Не удалось обработать как PCM данные: {e}")
                # Продолжаем, пытаясь обработать как обычный файл

        # Конвертируем аудио в нужный формат
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_data))
        audio_segment = (
            audio_segment.set_frame_rate(SAMPLE_RATE)
            .set_channels(CHANNELS)
            .set_sample_width(SAMPLE_WIDTH)
        )

        # Нормализуем уровень громкости
        audio_segment = audio_segment.normalize()

        # Сохраняем конвертированное аудио для диагностики
        audio_segment.export(f"{debug_prefix}_converted_{timestamp}.wav", format="wav")

    except CouldntDecodeError:
        logger.error(
            f"Невозможно декодировать аудио. Размер данных: {len(audio_data)} байт"
        )
        raise HTTPException(
            400,
            "Невозможно декодировать аудио. Поддерживаются форматы WAV, MP3, OGG и другие.",
        )
    except Exception as e:
        logger.error(
            f"Ошибка обработки аудио: {str(e)}, размер данных: {len(audio_data)} байт"
        )
        raise HTTPException(500, f"Ошибка обработки аудио: {str(e)}")

    # Преобразуем в numpy массив
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)

    # Логируем информацию о сэмплах
    logger.info(
        f"Получено {len(samples)} сэмплов аудио, длительность: {len(samples) / SAMPLE_RATE:.2f} сек"
    )

    # Проверяем минимальную длину аудио
    if len(samples) < MIN_AUDIO_LENGTH:
        logger.warning(
            f"Аудио слишком короткое: {len(samples)} сэмплов < {MIN_AUDIO_LENGTH} минимум"
        )
        raise HTTPException(
            400,
            f"Аудио слишком короткое, минимум 0.5 секунды ({MIN_AUDIO_LENGTH} сэмплов)",
        )

    return samples
