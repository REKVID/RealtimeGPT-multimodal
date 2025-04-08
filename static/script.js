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
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 3;
    let audioStream = null; // Храним ссылку на медиа-поток
    
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
            statusElement.textContent = 'Готов к записи';
            reconnectAttempts = 0; // Сбрасываем счетчик попыток при успешном подключении
        };
        
        socket.onmessage = async (event) => {
            console.log('Получены данные от сервера:', event.data instanceof Blob ? 'Blob данные' : event.data);
            
            if (event.data instanceof Blob) {
                try {
                    const arrayBuffer = await event.data.arrayBuffer();
                    console.log('Размер аудио в байтах:', arrayBuffer.byteLength);
                    
                    // Проверяем, что получен WAV-файл с заголовком
                    if (arrayBuffer.byteLength > 44) { // Минимальный размер WAV с заголовком
                        const header = new Uint8Array(arrayBuffer, 0, 44);
                        const headerString = String.fromCharCode.apply(null, header.slice(0, 4));
                        
                        if (headerString === 'RIFF') {
                            console.log('Получен корректный WAV-файл');
                            // Пропускаем заголовок WAV (44 байта) и преобразуем в Int16Array
                            const audioData = new Int16Array(arrayBuffer, 44);
                            playAudioBuffer(audioData);
                        } else {
                            console.log('Получен бинарный файл без заголовка WAV');
                            const audioData = new Int16Array(arrayBuffer);
                            playAudioBuffer(audioData);
                        }
                    } else {
                        console.error('Получены некорректные аудио данные');
                    }
                } catch (error) {
                    console.error('Ошибка при обработке аудио ответа:', error);
                }
            } else if (typeof event.data === 'string') {
                // Обрабатываем текстовые сообщения от сервера
                responseElement.style.display = 'block';
                responseTextElement.textContent = event.data;
            }
        };
        
        socket.onclose = (event) => {
            console.log(`WebSocket соединение закрыто с кодом ${event.code}`);
            
            // Пытаемся переподключиться, если соединение было разорвано неожиданно
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                const timeout = Math.min(1000 * reconnectAttempts, 5000); // Увеличиваем время между попытками
                statusElement.textContent = `Переподключение... попытка ${reconnectAttempts}`;
                
                setTimeout(() => {
                    console.log(`Попытка переподключения ${reconnectAttempts}...`);
                    initWebSocket();
                }, timeout);
            } else {
                statusElement.textContent = 'Не удалось установить соединение. Перезагрузите страницу.';
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
            audioPlayer = audioContext.createBufferSource();
        }
    }
    
    // Функция для воспроизведения аудио из Int16Array
    async function playAudioBuffer(int16Buffer) {
        initAudioContext();
        
        // Конвертируем из Int16 в Float32
        const floatBuffer = new Float32Array(int16Buffer.length);
        for (let i = 0; i < int16Buffer.length; i++) {
            floatBuffer[i] = int16Buffer[i] / 32768.0;
        }
        
        console.log('Размер аудио буфера:', floatBuffer.length);
        
        // Создаем аудио буфер
        const audioBuffer = audioContext.createBuffer(1, floatBuffer.length, 24000);
        audioBuffer.getChannelData(0).set(floatBuffer);
        
        // Создаем и запускаем источник
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start();
        
        // Показываем блок ответа
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
    
    // Функция для запуска записи
    async function startRecording() {
        const stream = await getMediaStream();
        if (!stream) return;
        
        isRecording = true;
        recordButton.textContent = 'Остановить запись';
        recordButton.classList.add('recording');
        statusElement.textContent = 'Запись...';
        
        audioChunks = [];
        
        // Настраиваем медиа-рекордер с указанием типа MIME и битрейта
        const options = {
            mimeType: 'audio/webm;codecs=opus',
            audioBitsPerSecond: 128000
        };
        
        try {
            mediaRecorder = new MediaRecorder(stream, options);
        } catch (e) {
            // Если формат не поддерживается, пробуем другие форматы
            console.warn('audio/webm;codecs=opus не поддерживается, используем стандартный формат');
            mediaRecorder = new MediaRecorder(stream);
        }
        
        console.log('Используется формат для записи:', mediaRecorder.mimeType);
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            // Создаем Blob из записанных частей
            const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
            
            console.log('Записано аудио:', audioBlob.size, 'байт, тип:', audioBlob.type);
            
            // Если аудио слишком короткое, предупреждаем пользователя
            if (audioBlob.size < 5000) {
                console.warn('Аудио слишком короткое, возможно проблемы с распознаванием');
                statusElement.textContent = 'Аудио слишком короткое, попробуйте говорить дольше';
                
                // Если совсем маленький размер, прерываем отправку
                if (audioBlob.size < 1000) {
                    console.error('Аудио слишком короткое для отправки');
                    setTimeout(() => {
                        statusElement.textContent = 'Готов к записи';
                    }, 2000);
                    return;
                }
            }
            
            try {
                // Конвертируем аудио в WAV формат для лучшей совместимости
                const wavBlob = await convertToWav(audioBlob);
                
                // Проверяем состояние соединения перед отправкой
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(wavBlob);
                    statusElement.textContent = 'Отправка аудио...';
                } else {
                    // Если соединение закрыто, пытаемся восстановить
                    statusElement.textContent = 'Переподключение...';
                    initWebSocket();
                    
                    // Пробуем отправить после небольшой задержки
                    setTimeout(() => {
                        if (socket && socket.readyState === WebSocket.OPEN) {
                            socket.send(wavBlob);
                            statusElement.textContent = 'Отправка аудио...';
                        } else {
                            statusElement.textContent = 'Не удалось отправить аудио. Попробуйте еще раз.';
                        }
                    }, 1000);
                }
            } catch (error) {
                console.error('Ошибка при подготовке аудио:', error);
                statusElement.textContent = 'Ошибка обработки аудио. Попробуйте еще раз.';
                return;
            }
            
            // Показываем блок транскрипции
            transcriptElement.style.display = 'block';
            transcriptTextElement.textContent = 'Обработка...';
        };
        
        // Запускаем запись с таймслайсами для больших файлов
        mediaRecorder.start(100);
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
}); 