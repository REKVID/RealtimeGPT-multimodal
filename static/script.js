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
    let audioQueue = [];
    let isPlaying = false;
    
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
                const arrayBuffer = await event.data.arrayBuffer();
                const audioBuffer = new Int16Array(arrayBuffer);
                
                // Добавляем аудио в очередь
                audioQueue.push(audioBuffer);
                
                // Если не воспроизводится, начинаем воспроизведение
                if (!isPlaying) {
                    playNextAudio();
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
    
    // Функция для инициализации аудио контекста
    function initAudioContext() {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
    }
    
    // Функция для воспроизведения следующего аудио из очереди
    async function playNextAudio() {
        if (audioQueue.length === 0) {
            isPlaying = false;
            return;
        }
        
        isPlaying = true;
        const audioBuffer = audioQueue.shift();
        
        initAudioContext();
        
        // Конвертируем из Int16 в Float32
        const floatBuffer = new Float32Array(audioBuffer.length);
        for (let i = 0; i < audioBuffer.length; i++) {
            floatBuffer[i] = audioBuffer[i] / 32768.0;
        }
        
        // Создаем аудио буфер
        const buffer = audioContext.createBuffer(1, floatBuffer.length, 24000);
        buffer.getChannelData(0).set(floatBuffer);
        
        // Создаем и запускаем источник
        const source = audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(audioContext.destination);
        
        // После окончания воспроизведения проверяем очередь
        source.onended = () => {
            playNextAudio();
        };
        
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
}); 
