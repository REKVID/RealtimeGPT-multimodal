"""
Модуль обработки аудио данных.

Этот модуль предоставляет функции для обработки аудио данных, включая
генерацию WAV-заголовков и нормализацию аудио сэмплов. Поддерживает
различные форматы входных данных и обеспечивает их конвертацию в
стандартный формат для дальнейшей обработки.

Attributes:
    SAMPLE_RATE (int): Частота дискретизации в Гц.
    CHANNELS (int): Количество аудио каналов.
    SAMPLE_WIDTH (int): Ширина сэмпла в байтах.
    MIN_AUDIO_LENGTH (int): Минимальная длина аудио в сэмплах.

Example:
    >>> header = generate_wav_header(24000, 16, 1, 48000)
    >>> samples = process_audio_data(audio_data)
"""

import io
import wave
import struct
import logging
import numpy as np
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from fastapi import HTTPException

from .config import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH, MIN_AUDIO_LENGTH

# Настройка логирования
logger = logging.getLogger("voice_app")


def generate_wav_header(n_samples):
    """
    sample_rate = SAMPLE_RATE
    bits_per_sample = 16
    channels = CHANNELS
    n_samples = len(combined_audio) - dimanic !!!!
    bits_per_sample = 16


    Генерирует WAV-заголовок для аудио данных.

    Args:
        sample_rate (int): Частота дискретизации в Гц.
        bits_per_sample (int): Количество бит на сэмпл.
        channels (int): Количество аудио каналов.
        n_samples (int): Количество сэмплов в аудио данных.

    Returns:
        bytes: WAV-заголовок в виде байтовой строки.

    Example:
        >>> header = generate_wav_header(24000, 16, 1, 48000)
        >>> with open('audio.wav', 'wb') as f:
        ...     f.write(header + audio_data)
    """
    datasize = n_samples * CHANNELS * 2
    header = bytes("RIFF", "ascii")
    header += struct.pack("<L", 36 + datasize)
    header += bytes("WAVE", "ascii")
    header += bytes("fmt ", "ascii")
    header += struct.pack("<L", 16)
    header += struct.pack("<H", 1)  # PCM формат
    header += struct.pack("<H", CHANNELS)
    header += struct.pack("<L", SAMPLE_RATE)
    header += struct.pack("<L", SAMPLE_RATE * CHANNELS * 2)
    header += struct.pack("<H", CHANNELS * 2)
    header += struct.pack("<H", 16)
    header += bytes("data", "ascii")
    header += struct.pack("<L", datasize)
    return header


def process_audio_data(audio_data):
    """Обрабатывает входные аудиоданные и возвращает нормализованные сэмплы.

    Функция поддерживает различные форматы входных данных (WAV, MP3, OGG, FLAC)
    и конвертирует их в стандартный формат с заданными параметрами.

    Args:
        audio_data (bytes): Входные аудиоданные в любом поддерживаемом формате.
        connection_id (Optional[str]): Идентификатор соединения для отладки.
        session (Optional[int]): Номер сессии для отладки.

    Returns:
        numpy.ndarray: Массив нормализованных аудио сэмплов.

    Raises:
        HTTPException: Если не удалось декодировать аудио или длина слишком мала.

    Example:
        >>> samples = process_audio_data(audio_data)
        >>> print(f"Получено {len(samples)} сэмплов")
    """
    try:
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

            # Создаем временный WAV-файл в памяти
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(SAMPLE_WIDTH)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(audio_data)

            # Читаем как AudioSegment
            wav_buffer.seek(0)
            audio_segment = AudioSegment.from_wav(wav_buffer)

        else:
            # Конвертируем аудио в нужный формат
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_data))
            audio_segment = (
                audio_segment.set_frame_rate(SAMPLE_RATE)
                .set_channels(CHANNELS)
                .set_sample_width(SAMPLE_WIDTH)
            )

        # Нормализуем уровень громкости
        audio_segment = audio_segment.normalize()

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
