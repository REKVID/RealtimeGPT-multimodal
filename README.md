# RealtimeGPT-multimodal



## Архитектура

### Основные компоненты

1. **FastAPI сервер** (`app/main.py`)
   - REST API для обработки аудио (`/process-audio/`)
   - WebSocket endpoint для real-time коммуникации (`/ws`)
   - Статический веб-интерфейс

2. **Голосовые агенты** (`app/voice_agents.py`)
   - `ExtendedVoiceWorkflow`: Обработка голосового взаимодействия
   - `main_agent`: Основной ассистент (GPT-4)
   - `client_agent`: Агент для работы с клиентами

### Технические характеристики

- Аудио формат: WAV (24kHz, 16bit, mono)
- Минимальная длина аудио: 0.5 секунд
- Поддержка потоковой передачи аудио

## Детальное описание функций

### Обработка аудио (`app/main.py`)

#### `process_audio_data(audio_data)`
```python
def process_audio_data(audio_data):
    """Обрабатывает входные аудиоданные и возвращает нормализованные сэмплы"""
```
- Конвертация аудио в WAV формат
- Нормализация параметров (24kHz, mono)
- Валидация длительности (>0.5с)
- Возвращает numpy массив сэмплов

#### `generate_wav_header(sample_rate, bits_per_sample, channels, n_samples)`
```python
def generate_wav_header(...):
    """Генерирует WAV-заголовок для аудио данных"""
```
- Создание стандартного WAV заголовка
- Установка параметров аудио
- Расчет размера данных

### API Endpoints

#### REST API (`/process-audio/`)
```python
@app.post("/process-audio/")
async def process_audio(audio: UploadFile):
```
- Загрузка аудио файла
- Обработка через голосовой конвейер
- Возврат синтезированного аудио

#### WebSocket API (`/ws`)
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
```
- Двусторонняя аудио коммуникация
- Потоковая обработка в реальном времени
- Автоматическая генерация WAV ответов

### Голосовой конвейер (`app/voice_agents.py`)

#### `ExtendedVoiceWorkflow`
```python
class ExtendedVoiceWorkflow(SingleAgentVoiceWorkflow):
```
- Наследует `SingleAgentVoiceWorkflow`
- Добавляет логирование транскрипций
- Потоковая обработка текста

#### Агенты

##### `main_agent`
- Основной ассистент на GPT-4
- Обработка пользовательских запросов
- Генерация контекстных ответов
- Поддержка русского языка

##### `client_agent`
- Специализированный агент для работы с клиентами
- Активируется по триггеру "чем могу помочь"
- Загружает инструкции из `instructions.txt`

### Вспомогательные функции

#### `read_instructions(index)`
```python
def read_instructions(index):
    """Загружает инструкции для агентов"""
```
- Чтение инструкций из файла
- Форматирование с handoff инструкциями
- Поддержка множественных инструкций

#### `create_voice_pipeline()`
```python
def create_voice_pipeline():
    """Создает экземпляр голосового конвейера"""
```
- Инициализация workflow
- Настройка основного агента
- Подготовка пайплайна для обработки



## Схема взаимодействия компонентов

```
[Клиент] <-> [FastAPI Server]
                  |
    [Обработка аудио (process_audio_data)]
                  |
    [Голосовой конвейер (VoicePipeline)]
                  |
         [ExtendedVoiceWorkflow]
                  |
    [main_agent] <-> [client_agent]
                  |
    [Синтез речи и отправка ответа]
```

## Примеры использования

### REST API
```python
import requests

files = {'audio': open('audio.wav', 'rb')}
response = requests.post('http://localhost:8001/process-audio/', files=files)
```

### WebSocket
```javascript
const ws = new WebSocket('ws://localhost:8001/ws');
ws.onmessage = function(event) {
    const audioBlob = event.data;
    // Обработка аудио ответа
};
``` 