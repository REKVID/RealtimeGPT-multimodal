document.addEventListener('DOMContentLoaded', () => {
    const startButton = document.getElementById('startButton');
    const stopButton = document.getElementById('stopButton');
    const statusElement = document.getElementById('status');
    const transcriptElement = document.getElementById('transcript');
    const transcriptTextElement = document.getElementById('transcriptText');
    const responseElement = document.getElementById('response');
    const responseTextElement = document.getElementById('responseText');
    
    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    let isConversationActive = false;
    let socket;
    let audioContext;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 3;
    let audioStream = null; // Храним ссылку на медиа-поток
    let silenceDetectionTimer = null;
    let audioProcessor = null;
    const SILENCE_THRESHOLD = 0.01; // Порог тишины
    const SILENCE_DURATION = 900; // Длительность тишины в мс для отправки
    
    // Функция для инициализации WebSocket с автоматическим переподключением
    function initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        // Закрываем существующее соединение, если оно открыто
        if (socket && socket.readyState !== WebSocket.CLOSED) {
            socket.close();
        }
        
        socket = new WebSocket(wsUrl);
        
        socket.onopen = () => {
            console.log('WebSocket соединение установлено');
            statusElement.textContent = 'Готов к разговору';
            reconnectAttempts = 0; // Сбрасываем счетчик попыток при успешном подключении
        };
        
        socket.onmessage = async (event) => {
            console.log('Получены данные от сервера:', event.data instanceof Blob ? 'Blob данные' : event.data);
            
            if (event.data instanceof Blob) {
                try {
                    const arrayBuffer = await event.data.arrayBuffer();
                    console.log('Размер аудио в байтах:', arrayBuffer.byteLength);
                    
                    if (arrayBuffer.byteLength > 44) {
                        const header = new Uint8Array(arrayBuffer, 0, 44);
                        const headerString = String.fromCharCode.apply(null, header.slice(0, 4));
                        
                        if (headerString === 'RIFF') {
                            console.log('Получен корректный WAV-файл');
                            const audioData = new Int16Array(arrayBuffer, 44);
                            await playAudioWithRetry(audioData);
                        } else {
                            console.log('Получен бинарный файл без заголовка WAV');
                            const audioData = new Int16Array(arrayBuffer);
                            await playAudioWithRetry(audioData);
                        }
                    } else {
                        console.error('Получены некорректные аудио данные');
                        if (isConversationActive) {
                            setTimeout(() => startRecordingWithSpeechDetection(), 1000);
                        }
                    }
                } catch (error) {
                    console.error('Ошибка при обработке аудио ответа:', error);
                    if (isConversationActive) {
                        setTimeout(() => startRecordingWithSpeechDetection(), 1000);
                    }
                }
                statusElement.textContent = 'Ответ (аудио)';
            } else if (typeof event.data === 'string') {
                responseElement.style.display = 'block';
                responseTextElement.textContent = event.data;
                statusElement.textContent = 'Ответ';
                
                // Если получили текстовое сообщение об ошибке, пробуем начать новую запись
                if (event.data.includes('Ошибка') && isConversationActive) {
                    setTimeout(() => startRecordingWithSpeechDetection(), 1000);
                }
            }
        };
        
        socket.onclose = (event) => {
            console.log(`WebSocket соединение закрыто с кодом ${event.code}`);
            
            // Пытаемся переподключиться, если соединение было разорвано неожиданно
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                const timeout = Math.min(1000 * reconnectAttempts, 5000);
                statusElement.textContent = `Переподключение... попытка ${reconnectAttempts}`;
                
                setTimeout(() => {
                    console.log(`Попытка переподключения ${reconnectAttempts}...`);
                    initWebSocket();
                }, timeout);
            } else {
                statusElement.textContent = 'Не удалось установить соединение. Перезагрузите страницу.';
                endConversation(); // Завершаем разговор при потере соединения
            }
        };
        
        socket.onerror = (error) => {
            console.error('WebSocket ошибка:', error);
        };
    }
    
    // Инициализируем WebSocket
    initWebSocket();
    
    // Функция для запроса разрешения на использование микрофона
    async function getMediaStream() {
        try {
            // Останавливаем предыдущий поток, если он существует
            if (audioStream) {
                audioStream.getTracks().forEach(track => track.stop());
            }
            
            // Запрашиваем новый поток с улучшенными параметрами
            audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 24000,
                    channelCount: 1
                }
            });
            
            return audioStream;
        } catch (err) {
            console.error('Ошибка доступа к микрофону:', err);
            statusElement.textContent = 'Ошибка доступа к микрофону. Пожалуйста, проверьте разрешения.';
            return null;
        }
    }
    
    // Функция для инициализации аудио контекста
    function initAudioContext() {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 24000
            });
        }
    }
    
    // Функция для воспроизведения аудио из Int16Array
    async function playAudioBuffer(int16Buffer) {
        initAudioContext();
        
        const floatBuffer = new Float32Array(int16Buffer.length);
        for (let i = 0; i < int16Buffer.length; i++) {
            floatBuffer[i] = int16Buffer[i] / 32768.0;
        }
        
        console.log('Размер аудио буфера:', floatBuffer.length);
        
        const audioBuffer = audioContext.createBuffer(1, floatBuffer.length, 24000);
        audioBuffer.getChannelData(0).set(floatBuffer);
        
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        
        source.onended = () => {
            console.log('Аудио воспроизведение завершено');
            if (isConversationActive) {
                setTimeout(() => {
                    if (isConversationActive) {
                        startRecordingWithSpeechDetection();
                    }
                }, 500);
            }
        };
        
        source.start();
        
        responseElement.style.display = 'block';
        responseTextElement.textContent = 'Воспроизводится аудио-ответ...';
    }
    
    // Функция для конвертации Blob в WAV формат
    async function convertToWav(audioBlob) {
        return new Promise((resolve, reject) => {
            // Преобразуем Blob в ArrayBuffer
            const fileReader = new FileReader();
            fileReader.onload = async (event) => {
                try {
                    const arrayBuffer = event.target.result;
                    
                    // Создаем аудио контекст для декодирования
                    const tempContext = new (window.AudioContext || window.webkitAudioContext)({
                        sampleRate: 24000
                    });
                    
                    // Декодируем аудио данные
                    const audioBuffer = await tempContext.decodeAudioData(arrayBuffer);
                    
                    // Создаем массив сэмплов (объединяем каналы в моно, если нужно)
                    const numChannels = audioBuffer.numberOfChannels;
                    const length = audioBuffer.length;
                    const sampleRate = audioBuffer.sampleRate;
                    const monoData = new Float32Array(length);
                    
                    // Если аудио стерео, конвертируем в моно
                    if (numChannels === 2) {
                        const left = audioBuffer.getChannelData(0);
                        const right = audioBuffer.getChannelData(1);
                        for (let i = 0; i < length; i++) {
                            monoData[i] = (left[i] + right[i]) / 2;
                        }
                    } else {
                        // Если моно, просто копируем
                        monoData.set(audioBuffer.getChannelData(0));
                    }
                    
                    // Преобразуем Float32Array в Int16Array для WAV
                    const int16Data = new Int16Array(length);
                    for (let i = 0; i < length; i++) {
                        // Масштабируем и преобразуем в Int16
                        const sample = Math.max(-1, Math.min(1, monoData[i])) * 32767;
                        int16Data[i] = Math.floor(sample);
                    }
                    
                    // Создаем WAV заголовок
                    const wavHeader = new ArrayBuffer(44);
                    const view = new DataView(wavHeader);
                    
                    // "RIFF" chunk descriptor
                    writeString(view, 0, "RIFF");
                    view.setUint32(4, 36 + int16Data.length * 2, true);
                    writeString(view, 8, "WAVE");
                    
                    // "fmt " sub-chunk
                    writeString(view, 12, "fmt ");
                    view.setUint32(16, 16, true); // Размер fmt 
                    view.setUint16(20, 1, true); // PCM формат
                    view.setUint16(22, 1, true); // Моно
                    view.setUint32(24, 24000, true); // Частота дискретизации
                    view.setUint32(28, 24000 * 2, true); // Байт/сек
                    view.setUint16(32, 2, true); // Выравнивание
                    view.setUint16(34, 16, true); // Бит на сэмпл
                    
                    // "data" sub-chunk
                    writeString(view, 36, "data");
                    view.setUint32(40, int16Data.length * 2, true);
                    
                    // Объединяем заголовок и данные
                    const wavData = new Uint8Array(44 + int16Data.length * 2);
                    wavData.set(new Uint8Array(wavHeader), 0);
                    wavData.set(new Uint8Array(int16Data.buffer), 44);
                    
                    // Создаем Blob с правильным типом
                    const wavBlob = new Blob([wavData], { type: 'audio/wav' });
                    console.log('Сконвертировано в WAV:', wavBlob.size, 'байт');
                    
                    resolve(wavBlob);
                } catch (error) {
                    console.error('Ошибка конвертации аудио:', error);
                    reject(error);
                }
            };
            
            fileReader.onerror = reject;
            fileReader.readAsArrayBuffer(audioBlob);
        });
        
        function writeString(view, offset, string) {
            for (let i = 0; i < string.length; i++) {
                view.setUint8(offset + i, string.charCodeAt(i));
            }
        }
    }
    
    // Функция для обнаружения тишины
    function setupSilenceDetection(stream) {
        if (audioProcessor) {
            audioProcessor.disconnect();
            audioProcessor = null;
        }
        
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 24000
            });
        }
        
        const source = audioContext.createMediaStreamSource(stream);
        audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
        
        let silenceStart = null;
        let isSilent = false;
        
        audioProcessor.onaudioprocess = (event) => {
            if (!isRecording) return;
            
            const input = event.inputBuffer.getChannelData(0);
            let sum = 0;
            
            // Вычисляем громкость звука
            for (let i = 0; i < input.length; i++) {
                sum += input[i] * input[i];
            }
            
            const rms = Math.sqrt(sum / input.length);
            
            // Определяем тишину
            if (rms < SILENCE_THRESHOLD) {
                if (!isSilent) {
                    isSilent = true;
                    silenceStart = Date.now();
                } else if (Date.now() - silenceStart > SILENCE_DURATION) {
                    // Если тишина длится дольше порогового значения
                    if (isRecording && mediaRecorder.state !== 'inactive') {
                        console.log('Обнаружена пауза, отправляем запись');
                        stopRecording();
                    }
                }
            } else {
                isSilent = false;
                silenceStart = null;
            }
        };
        
        source.connect(audioProcessor);
        audioProcessor.connect(audioContext.destination);
    }
    
    // Функция для мониторинга начала речи
    async function waitForSpeech() {
        const stream = await getMediaStream();
        if (!stream) return;
        
        return new Promise((resolve) => {
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: 24000
                });
            }
            
            const source = audioContext.createMediaStreamSource(stream);
            const processor = audioContext.createScriptProcessor(1024, 1, 1); // Уменьшаем размер буфера для более быстрой реакции
            let speechDetected = false;
            let consecutiveFramesAboveThreshold = 0;
            const SPEECH_THRESHOLD = 0.003; // Более чувствительный порог
            const REQUIRED_FRAMES = 2; // Меньше фреймов для быстрой реакции
            
            // Буфер для хранения последних семплов
            const sampleBuffer = new Float32Array(48000); // 2 секунды при 24кГц
            let sampleBufferIndex = 0;
            
            processor.onaudioprocess = (event) => {
                if (speechDetected) return;
                
                const input = event.inputBuffer.getChannelData(0);
                let sum = 0;
                
                // Копируем входные данные в буфер
                for (let i = 0; i < input.length; i++) {
                    sampleBuffer[sampleBufferIndex] = input[i];
                    sampleBufferIndex = (sampleBufferIndex + 1) % sampleBuffer.length;
                    sum += input[i] * input[i];
                }
                
                const rms = Math.sqrt(sum / input.length);
                
                if (rms > SPEECH_THRESHOLD) {
                    consecutiveFramesAboveThreshold++;
                    if (consecutiveFramesAboveThreshold >= REQUIRED_FRAMES) {
                        speechDetected = true;
                        console.log('Обнаружено начало речи');
                        
                        // Отключаем процессор
                        processor.disconnect();
                        source.disconnect();
                        
                        // Создаем буфер с предварительно записанными данными
                        const audioBuffer = audioContext.createBuffer(1, sampleBuffer.length, audioContext.sampleRate);
                        const channelData = audioBuffer.getChannelData(0);
                        
                        // Копируем данные из кольцевого буфера в правильном порядке
                        for (let i = 0; i < sampleBuffer.length; i++) {
                            const index = (sampleBufferIndex + i) % sampleBuffer.length;
                            channelData[i] = sampleBuffer[index];
                        }
                        
                        resolve({
                            stream: stream,
                            audioBuffer: audioBuffer
                        });
                    }
                } else {
                    consecutiveFramesAboveThreshold = Math.max(0, consecutiveFramesAboveThreshold - 1);
                }
            };
            
            source.connect(processor);
            processor.connect(audioContext.destination);
            
            // Таймаут для автоматического перезапуска, если речь не обнаружена
            setTimeout(() => {
                if (!speechDetected) {
                    processor.disconnect();
                    source.disconnect();
                    resolve({ stream: stream });
                }
            }, 10000); // 10 секунд максимального ожидания
        });
    }
    
    // Функция для запуска записи с ожиданием начала речи
    async function startRecordingWithSpeechDetection() {
        statusElement.textContent = 'Ожидание речи...';
        console.log('Ожидание начала речи...');
        
        try {
            const streamData = await waitForSpeech();
            if (streamData && isConversationActive) {
                startRecording(streamData);
            }
        } catch (error) {
            console.error('Ошибка при определении начала речи:', error);
            if (isConversationActive) {
                setTimeout(startRecordingWithSpeechDetection, 1000);
            }
        }
    }
    
    // Функция для запуска записи с предзаписанными данными
    async function startRecording(streamData) {
        if (!streamData) return;
        
        const stream = streamData.stream;
        
        isRecording = true;
        statusElement.textContent = 'Запись...';
        
        audioChunks = [];
        
        // Настраиваем медиа-рекордер
        let options;
        try {
            options = {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 128000
            };
            mediaRecorder = new MediaRecorder(stream, options);
        } catch (e) {
            console.warn('audio/webm;codecs=opus не поддерживается, пробуем другие форматы');
            try {
                options = {
                    mimeType: 'audio/webm',
                    audioBitsPerSecond: 128000
                };
                mediaRecorder = new MediaRecorder(stream, options);
            } catch (e) {
                console.warn('audio/webm не поддерживается, используем стандартный формат');
                mediaRecorder = new MediaRecorder(stream);
            }
        }
        
        console.log('Используется формат для записи:', mediaRecorder.mimeType);
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            if (audioChunks.length === 0) {
                console.warn('Нет данных для отправки');
                if (isConversationActive) {
                    setTimeout(() => startRecordingWithSpeechDetection(), 500);
                }
                return;
            }
            
            // Создаем Blob из всех частей записи
            const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
            console.log('Записано аудио:', audioBlob.size, 'байт, тип:', audioBlob.type);
            
            // Если аудио слишком короткое, начинаем новую запись
            if (audioBlob.size < 5000) {
                console.warn('Аудио слишком короткое, записываем снова...');
                if (isConversationActive) {
                    setTimeout(() => startRecordingWithSpeechDetection(), 500);
                }
                return;
            }
            
            try {
                // Конвертируем аудио в WAV формат
                const wavBlob = await convertToWav(audioBlob);
                
                // Проверяем состояние соединения перед отправкой
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(wavBlob);
                    statusElement.textContent = 'Обработка...';
                } else {
                    // Если соединение закрыто, пытаемся восстановить
                    statusElement.textContent = 'Переподключение...';
                    initWebSocket();
                    
                    // Пробуем отправить после небольшой задержки
                    setTimeout(() => {
                        if (socket && socket.readyState === WebSocket.OPEN) {
                            socket.send(wavBlob);
                            statusElement.textContent = 'Обработка...';
                        } else {
                            statusElement.textContent = 'Не удалось отправить аудио. Попробуйте еще раз.';
                            if (isConversationActive) {
                                setTimeout(() => startRecordingWithSpeechDetection(), 1000);
                            }
                        }
                    }, 1000);
                }
            } catch (error) {
                console.error('Ошибка при подготовке аудио:', error);
                statusElement.textContent = 'Ошибка обработки аудио. Попробуйте еще раз.';
                if (isConversationActive) {
                    setTimeout(() => startRecordingWithSpeechDetection(), 1000);
                }
                return;
            }
            
            // Показываем блок транскрипции
            transcriptElement.style.display = 'block';
            transcriptTextElement.textContent = 'Обработка...';
        };
        
        // Настраиваем обнаружение тишины
        setupSilenceDetection(stream);
        
        // Запускаем запись
        mediaRecorder.start(100);
    }
    
    // Функция для остановки записи
    function stopRecording() {
        if (mediaRecorder && isRecording && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            isRecording = false;
            statusElement.textContent = 'Обработка аудио...';
        }
    }
    
    // Функция начала разговора
    function startConversation() {
        isConversationActive = true;
        startButton.style.display = 'none';
        stopButton.style.display = 'block';
        statusElement.textContent = 'Начало разговора...';
        startRecordingWithSpeechDetection();
    }
    
    // Функция окончания разговора
    function endConversation() {
        isConversationActive = false;
        startButton.style.display = 'block';
        stopButton.style.display = 'none';
        
        if (isRecording) {
            stopRecording();
        }
        
        if (audioProcessor) {
            audioProcessor.disconnect();
            audioProcessor = null;
        }
        
        // Останавливаем аудиопоток
        if (audioStream) {
            audioStream.getTracks().forEach(track => track.stop());
            audioStream = null;
        }
        
        statusElement.textContent = 'Разговор завершен';
    }
    
    // Функция воспроизведения аудио с повторными попытками
    async function playAudioWithRetry(int16Buffer, maxRetries = 3) {
        let retryCount = 0;
        let lastError = null;
        
        while (retryCount < maxRetries) {
            try {
                await playAudioBuffer(int16Buffer);
                return; // Успешно воспроизвели аудио
            } catch (error) {
                lastError = error;
                console.error(`Ошибка воспроизведения аудио (попытка ${retryCount + 1}/${maxRetries}):`, error);
                retryCount++;
                if (retryCount < maxRetries) {
                    await new Promise(resolve => setTimeout(resolve, 1000 * retryCount));
                }
            }
        }
        
        // Если все попытки не удались, начинаем новую запись
        console.error('Не удалось воспроизвести аудио после всех попыток:', lastError);
        if (isConversationActive) {
            setTimeout(() => startRecordingWithSpeechDetection(), 1000);
        }
    }
    
    // Обработчики для кнопок
    startButton.addEventListener('click', startConversation);
    stopButton.addEventListener('click', endConversation);
    
    // Инициализация кнопок
    stopButton.style.display = 'none';
}); 