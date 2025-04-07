document.addEventListener('DOMContentLoaded', () => {
    const recordButton = document.getElementById('recordButton');
    const statusElement = document.getElementById('status');
    const transcriptElement = document.getElementById('transcript');
    const transcriptTextElement = document.getElementById('transcriptText');
    const responseElement = document.getElementById('response');
    const responseTextElement = document.getElementById('responseText');
    
    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    let socket;
    let audioContext;
    let audioPlayer;
    let audioBuffers = []; // Буфер для хранения аудиофрагментов
    let isPlayingAudio = false;
    let pingInterval; // Интервал для пинга сервера
    let reconnectTimeout; // Таймаут для переподключения
    
    // Функция для инициализации WebSocket
    function initWebSocket() {
        // Очищаем предыдущие таймеры, если они есть
        if (pingInterval) clearInterval(pingInterval);
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        socket = new WebSocket(wsUrl);
        
        socket.onopen = () => {
            console.log('WebSocket соединение установлено');
            
            // Запускаем пинг каждые 30 секунд для поддержания соединения
            pingInterval = setInterval(() => {
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({ action: "ping" }));
                    console.log('Ping отправлен');
                }
            }, 30000);
        };
        
        socket.onmessage = async (event) => {
            // Если получен бинарный аудиопоток
            if (event.data instanceof Blob) {
                const arrayBuffer = await event.data.arrayBuffer();
                console.log(`Получен аудиобуфер размером: ${arrayBuffer.byteLength} байт`);
                
                // Создаем объект для распознавания WAV-заголовка
                const isWavHeader = (buffer) => {
                    const header = new Uint8Array(buffer.slice(0, 4));
                    const headerString = String.fromCharCode(...header);
                    return headerString === 'RIFF';
                };
                
                // Проверяем, содержит ли буфер WAV-заголовок
                const hasWavHeader = isWavHeader(arrayBuffer);
                
                if (hasWavHeader) {
                    // Если это первый фрагмент с заголовком, создаем новый буфер
                    audioBuffers = [];
                    
                    // Находим начало аудиоданных после заголовка (обычно 44 байта)
                    const dataStart = new Uint8Array(arrayBuffer).findIndex((value, index, array) => {
                        if (index >= array.length - 3) return false;
                        return array[index] === 100 && // 'd'
                               array[index + 1] === 97 && // 'a'
                               array[index + 2] === 116 && // 't'
                               array[index + 3] === 97; // 'a'
                    });
                    
                    const headerSize = dataStart + 8; // 8 байт для "data" + размер данных
                    console.log(`WAV заголовок размером: ${headerSize} байт`);
                    
                    // Пропускаем заголовок и получаем аудиоданные
                    const audioData = arrayBuffer.slice(headerSize);
                    const audioBuffer = new Int16Array(audioData);
                    
                    // Добавляем в буфер воспроизведения
                    audioBuffers.push(audioBuffer);
                    
                    // Начинаем воспроизведение если оно еще не идет
                    if (!isPlayingAudio) {
                        isPlayingAudio = true;
                        playNextAudioBuffer();
                    }
                } else {
                    // Если это продолжение аудиопотока, просто добавляем в буфер
                    const audioBuffer = new Int16Array(arrayBuffer);
                    audioBuffers.push(audioBuffer);
                }
            }
            // Если получено JSON-сообщение с информацией о состоянии
            else if (typeof event.data === 'string') {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Получены данные о состоянии:', data);
                    
                    // Обработка статусов
                    if (data.status) {
                        switch (data.status) {
                            case 'processing':
                                statusElement.textContent = 'Обработка запроса...';
                                responseElement.style.display = 'block';
                                responseTextElement.textContent = 'Ожидание ответа...';
                                break;
                            case 'completed':
                                statusElement.textContent = 'Готов к записи';
                                responseTextElement.textContent = 'Ответ получен.';
                                isPlayingAudio = false;
                                break;
                            case 'cancelled':
                                statusElement.textContent = 'Запрос отменен';
                                break;
                            case 'stopped':
                                statusElement.textContent = 'Готов к записи';
                                break;
                        }
                    }
                    
                    // Обработка ошибок
                    if (data.error) {
                        statusElement.textContent = `Ошибка: ${data.error}`;
                        console.error('Ошибка от сервера:', data.error);
                    }
                    
                    // Обработка событий жизненного цикла
                    if (data.lifecycle) {
                        console.log('Событие жизненного цикла:', data.lifecycle);
                        switch (data.lifecycle) {
                            case 'turn_started':
                                console.log('Начало речи модели');
                                break;
                            case 'turn_ended':
                                console.log('Конец речи модели');
                                break;
                            default:
                                console.log('Другое событие жизненного цикла:', data.lifecycle);
                        }
                    }
                } catch (e) {
                    console.error('Ошибка при разборе JSON сообщения:', e);
                }
            }
        };
        
        socket.onclose = (event) => {
            console.log(`WebSocket соединение закрыто. Код: ${event.code}, Причина: ${event.reason}`);
            
            // Очищаем интервал пинга
            if (pingInterval) {
                clearInterval(pingInterval);
                pingInterval = null;
            }
            
            // Планируем переподключение через 2 секунды
            reconnectTimeout = setTimeout(() => {
                console.log('Попытка переподключения WebSocket...');
                initWebSocket();
            }, 2000);
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
            return await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            console.error('Ошибка доступа к микрофону:', err);
            statusElement.textContent = 'Ошибка доступа к микрофону. Пожалуйста, проверьте разрешения.';
            return null;
        }
    }
    
    // Функция для инициализации аудио контекста
    function initAudioContext() {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
    }
    
    // Функция для последовательного воспроизведения буферов
    async function playNextAudioBuffer() {
        if (!isPlayingAudio || audioBuffers.length === 0) {
            isPlayingAudio = false;
            return;
        }
        
        // Берем следующий буфер из очереди
        const int16Buffer = audioBuffers.shift();
        
        initAudioContext();
        
        // Конвертируем из Int16 в Float32
        const floatBuffer = new Float32Array(int16Buffer.length);
        for (let i = 0; i < int16Buffer.length; i++) {
            floatBuffer[i] = int16Buffer[i] / 32768.0;
        }
        
        // Создаем аудио буфер
        const audioBuffer = audioContext.createBuffer(1, floatBuffer.length, 24000);
        audioBuffer.getChannelData(0).set(floatBuffer);
        
        // Создаем источник
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        
        // После окончания воспроизведения буфера
        source.onended = () => {
            // Проверяем, есть ли еще буферы для воспроизведения
            if (audioBuffers.length > 0) {
                playNextAudioBuffer();
            } else if (isPlayingAudio) {
                // Если буферов нет, но воспроизведение не остановлено явно
                // ждем некоторое время для получения новых данных
                setTimeout(() => {
                    if (audioBuffers.length > 0) {
                        playNextAudioBuffer();
                    } else {
                        isPlayingAudio = false;
                    }
                }, 100);
            }
        };
        
        // Запускаем воспроизведение
        source.start();
        
        // Показываем блок ответа
        responseElement.style.display = 'block';
        responseTextElement.textContent = 'Воспроизводится аудио-ответ...';
    }
    
    // Функция для запуска записи
    async function startRecording() {
        const stream = await getMediaStream();
        if (!stream) return;
        
        isRecording = true;
        recordButton.textContent = 'Остановить запись';
        recordButton.classList.add('recording');
        statusElement.textContent = 'Запись...';
        
        // Очищаем буферы
        audioChunks = [];
        
        // Настраиваем медиарекордер
        const options = { mimeType: 'audio/webm' };
        mediaRecorder = new MediaRecorder(stream, options);
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            // Создаем Blob из записанных частей
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            
            // Отправляем аудио через WebSocket
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(audioBlob);
                statusElement.textContent = 'Отправка аудио...';
            } else {
                statusElement.textContent = 'WebSocket соединение не установлено. Попробуйте перезагрузить страницу.';
                // Переподключаем сокет
                initWebSocket();
            }
            
            // Показываем блок транскрипции
            transcriptElement.style.display = 'block';
            transcriptTextElement.textContent = 'Обработка...';
        };
        
        // Запрашиваем данные каждые 250мс для более плавной передачи
        mediaRecorder.start(250);
    }
    
    // Функция для остановки записи
    function stopRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            recordButton.textContent = 'Нажмите для записи';
            recordButton.classList.remove('recording');
            statusElement.textContent = 'Обработка аудио...';
        }
    }
    
    // Обработчик клика по кнопке записи
    recordButton.addEventListener('click', () => {
        if (!isRecording) {
            startRecording();
        } else {
            stopRecording();
        }
    });
    
    // Функция для остановки текущего воспроизведения
    function stopPlayback() {
        if (isPlayingAudio) {
            isPlayingAudio = false;
            audioBuffers = [];
            
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({action: 'stop'}));
            }
        }
    }
    
    // Функция для отправки аудио на сервер через HTTP (альтернативный метод)
    async function sendAudioToServer(audioBlob) {
        try {
            const formData = new FormData();
            formData.append('audio', audioBlob);
            
            statusElement.textContent = 'Отправка аудио...';
            
            const response = await fetch('/process-audio/', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const audioBlob = await response.blob();
                const audioUrl = URL.createObjectURL(audioBlob);
                
                const audio = new Audio(audioUrl);
                audio.oncanplaythrough = () => {
                    responseElement.style.display = 'block';
                    responseTextElement.textContent = 'Воспроизводится аудио-ответ...';
                    audio.play();
                };
                
                audio.onended = () => {
                    responseTextElement.textContent = 'Ответ получен.';
                    statusElement.textContent = 'Готов к записи';
                };
            } else {
                statusElement.textContent = 'Ошибка при отправке аудио';
            }
        } catch (error) {
            console.error('Ошибка при отправке аудио:', error);
            statusElement.textContent = 'Ошибка при отправке аудио';
        }
    }
}); 