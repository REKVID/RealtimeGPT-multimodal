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
    
    // Аудио обработчик для потокового воспроизведения
    class AudioStreamPlayer {
        constructor() {
            this.audioContext = null;
            this.audioQueue = [];
            this.isPlaying = false;
            this.gainNode = null;
            this.bufferSize = 0;
            this.lastPlayTime = 0;
            // Минимальная длительность буфера для воспроизведения (секунды)
            this.minBufferDuration = 0.05;
            // Максимальная длительность буфера для объединения (секунды)
            this.maxCombinedDuration = 1.0;
            // Накопленный буфер для маленьких фрагментов
            this.accumulatedBuffer = null;
            this.accumulatedDuration = 0;
            this.init();
        }
        
        init() {
            // Создаем контекст при первом взаимодействии пользователя
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 24000
            });
            
            // Создаем усилитель
            this.gainNode = this.audioContext.createGain();
            this.gainNode.gain.value = 1.0;
            this.gainNode.connect(this.audioContext.destination);
            
            console.log('AudioStreamPlayer инициализирован с частотой дискретизации:', this.audioContext.sampleRate);
        }
        
        async processAudioChunk(arrayBuffer) {
            try {
                // Проверяем наличие WAV-заголовка и пропускаем его
                const dataView = new DataView(arrayBuffer);
                let offset = 0;
                
                // WAV заголовок начинается с 'RIFF'
                const riff = String.fromCharCode(
                    dataView.getUint8(0),
                    dataView.getUint8(1),
                    dataView.getUint8(2),
                    dataView.getUint8(3)
                );
                
                if (riff === 'RIFF') {
                    // Поиск начала данных
                    for (let i = 0; i < arrayBuffer.byteLength - 4; i++) {
                        const fourChars = String.fromCharCode(
                            dataView.getUint8(i),
                            dataView.getUint8(i + 1),
                            dataView.getUint8(i + 2),
                            dataView.getUint8(i + 3)
                        );
                        
                        if (fourChars === 'data') {
                            // Нашли начало данных
                            // data + size (4 байта) = 8 байт до начала аудиоданных
                            offset = i + 8;
                            break;
                        }
                    }
                    
                    console.log(`WAV заголовок обнаружен, начало данных с байта ${offset}`);
                } else {
                    console.log('WAV заголовок не обнаружен, обрабатываю как сырые данные');
                }
                
                // Получаем данные аудио, пропустив заголовок
                const audioData = arrayBuffer.slice(offset);
                
                // Конвертируем данные в Int16Array
                const int16Data = new Int16Array(audioData);
                console.log(`Получен аудиофрагмент размером ${int16Data.length} сэмплов`);
                
                // Создаем Float32Array для Web Audio API
                const floatData = new Float32Array(int16Data.length);
                for (let i = 0; i < int16Data.length; i++) {
                    floatData[i] = int16Data[i] / 32768.0;
                }
                
                // Создаем буфер аудио
                const audioBuffer = this.audioContext.createBuffer(1, floatData.length, 24000);
                audioBuffer.getChannelData(0).set(floatData);
                
                // Воспроизводим сразу с правильным таймингом
                this.scheduleBuffer(audioBuffer);
            } catch (error) {
                console.error('Ошибка обработки аудио:', error);
            }
        }
        
        scheduleBuffer(audioBuffer) {
            try {
                // Проверяем длительность буфера
                const bufferDuration = audioBuffer.duration;
                
                // Если буфер слишком короткий и не первый, накапливаем его
                if (bufferDuration < this.minBufferDuration && this.bufferSize > 0) {
                    if (!this.accumulatedBuffer) {
                        // Создаем новый накопительный буфер
                        this.accumulatedBuffer = audioBuffer;
                        this.accumulatedDuration = bufferDuration;
                    } else {
                        // Объединяем буферы
                        this.combineBuffers(audioBuffer);
                    }
                    
                    // Если накопленный буфер достаточно большой или это последний фрагмент, воспроизводим его
                    if (this.accumulatedDuration >= this.maxCombinedDuration) {
                        this.playAccumulatedBuffer();
                    }
                } else {
                    // Если есть накопленный буфер, сначала воспроизводим его
                    if (this.accumulatedBuffer) {
                        this.playAccumulatedBuffer();
                    }
                    
                    // Воспроизводим текущий буфер напрямую
                    this.playBuffer(audioBuffer);
                }
            } catch (error) {
                console.error('Ошибка планирования воспроизведения:', error);
            }
        }
        
        // Объединяет текущий буфер с накопленным
        combineBuffers(newBuffer) {
            const accLength = this.accumulatedBuffer.length;
            const newLength = newBuffer.length;
            const totalLength = accLength + newLength;
            
            // Создаем новый буфер
            const combinedBuffer = this.audioContext.createBuffer(
                1, totalLength, this.audioContext.sampleRate
            );
            
            // Копируем данные из накопленного буфера
            const combinedData = combinedBuffer.getChannelData(0);
            combinedData.set(this.accumulatedBuffer.getChannelData(0), 0);
            
            // Добавляем данные из нового буфера
            combinedData.set(newBuffer.getChannelData(0), accLength);
            
            // Обновляем накопленный буфер и его длительность
            this.accumulatedBuffer = combinedBuffer;
            this.accumulatedDuration += newBuffer.duration;
            
            console.log(`Буферы объединены: общая длительность ${this.accumulatedDuration}с`);
        }
        
        // Воспроизводит накопленный буфер
        playAccumulatedBuffer() {
            if (!this.accumulatedBuffer) return;
            
            this.playBuffer(this.accumulatedBuffer);
            
            // Сбрасываем накопленный буфер
            this.accumulatedBuffer = null;
            this.accumulatedDuration = 0;
        }
        
        // Воспроизводит буфер с правильным таймингом
        playBuffer(audioBuffer) {
            const now = this.audioContext.currentTime;
            // Планируем воспроизведение сразу после текущего буфера
            const startTime = Math.max(now, this.lastPlayTime);
            
            // Создаем источник звука
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.gainNode);
            
            // Запускаем воспроизведение в запланированное время
            source.start(startTime);
            
            // Обновляем время окончания текущего буфера
            const bufferDuration = audioBuffer.duration;
            this.lastPlayTime = startTime + bufferDuration;
            
            this.bufferSize += 1;
            
            // Показываем блок ответа и обновляем статус
            responseElement.style.display = 'block';
            responseTextElement.textContent = `Воспроизводится аудио-ответ (фрагмент ${this.bufferSize})...`;
            
            console.log(`Запланировано воспроизведение фрагмента ${this.bufferSize} в ${startTime}, длительность ${bufferDuration}с`);
        }
        
        resetContext() {
            if (this.audioContext && this.audioContext.state === 'suspended') {
                this.audioContext.resume().then(() => {
                    console.log('AudioContext возобновлен');
                });
            }
            
            // Сбрасываем счетчики и буферы
            this.bufferSize = 0;
            this.lastPlayTime = this.audioContext ? this.audioContext.currentTime : 0;
            this.accumulatedBuffer = null;
            this.accumulatedDuration = 0;
            
            console.log('Аудио контекст сброшен');
        }
    }
    
    // Создаем экземпляр аудиоплеера
    const audioPlayer = new AudioStreamPlayer();
    
    // Функция для инициализации WebSocket
    function initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        socket = new WebSocket(wsUrl);
        
        socket.onopen = () => {
            console.log('WebSocket соединение установлено');
        };
        
        socket.onmessage = async (event) => {
            if (event.data instanceof Blob) {
                console.log('Получен аудиофрагмент');
                const arrayBuffer = await event.data.arrayBuffer();
                audioPlayer.processAudioChunk(arrayBuffer);
            } else if (typeof event.data === 'string') {
                try {
                    const message = JSON.parse(event.data);
                    if (message.type === 'transcript') {
                        transcriptElement.style.display = 'block';
                        transcriptTextElement.textContent = message.text;
                    } else if (message.type === 'status') {
                        console.log(`Статус: ${message.text}`);
                        
                        if (message.text === 'Начало ответа') {
                            // Сбрасываем аудиоконтекст для нового ответа
                            audioPlayer.resetContext();
                            
                            // Проверяем и возобновляем контекст аудио, если он приостановлен
                            if (audioPlayer.audioContext.state === 'suspended') {
                                await audioPlayer.audioContext.resume();
                                console.log('AudioContext возобновлен при получении ответа');
                            }
                            
                            // Создаем короткий звуковой сигнал для уведомления
                            const notificationBuffer = createNotificationSound(audioPlayer.audioContext);
                            audioPlayer.playBuffer(notificationBuffer);
                            
                            responseElement.style.display = 'block';
                            responseTextElement.textContent = 'Начинаю получать ответ...';
                        } else if (message.text === 'Ответ завершен') {
                            // Воспроизводим накопленный буфер, если он есть
                            if (audioPlayer.accumulatedBuffer) {
                                audioPlayer.playAccumulatedBuffer();
                            }
                            
                            setTimeout(() => {
                                responseTextElement.textContent = 'Ответ завершен';
                            }, 1000);
                        }
                    }
                } catch (e) {
                    console.error('Ошибка парсинга сообщения:', e);
                }
            }
        };
        
        socket.onclose = () => {
            console.log('WebSocket соединение закрыто');
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
    
    // Функция для запуска записи
    async function startRecording() {
        // Сбрасываем аудиоконтекст для нового ответа
        audioPlayer.resetContext();
        
        const stream = await getMediaStream();
        if (!stream) return;
        
        isRecording = true;
        recordButton.textContent = 'Остановить запись';
        recordButton.classList.add('recording');
        statusElement.textContent = 'Запись...';
        
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream);
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            // Создаем Blob из записанных частей
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            
            // Отправляем аудио через WebSocket
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(audioBlob);
                statusElement.textContent = 'Отправка аудио...';
            } else {
                statusElement.textContent = 'WebSocket соединение не установлено. Попробуйте перезагрузить страницу.';
            }
            
            // Показываем блок транскрипции
            transcriptElement.style.display = 'block';
            transcriptTextElement.textContent = 'Обработка...';
        };
        
        mediaRecorder.start();
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
    
    // Добавляем обработчик первого взаимодействия для автозапуска аудиоконтекста
    document.addEventListener('click', function initAudioContext() {
        if (audioPlayer && audioPlayer.audioContext && audioPlayer.audioContext.state === 'suspended') {
            audioPlayer.audioContext.resume().then(() => {
                console.log('AudioContext возобновлен после взаимодействия с пользователем');
            });
            document.removeEventListener('click', initAudioContext);
        }
    }, { once: false });
    
    // Функция для создания короткого звукового сигнала-уведомления
    function createNotificationSound(audioContext) {
        const duration = 0.2;  // секунды
        const sampleRate = audioContext.sampleRate;
        const bufferSize = duration * sampleRate;
        const buffer = audioContext.createBuffer(1, bufferSize, sampleRate);
        
        // Создаем небольшой звуковой сигнал
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            // Затухающий сигнал с частотой 800 Гц
            const t = i / sampleRate;
            data[i] = 0.1 * Math.sin(2 * Math.PI * 800 * t) * Math.exp(-10 * t);
        }
        
        return buffer;
    }
}); 
