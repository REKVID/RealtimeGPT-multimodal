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
                
                // Воспроизводим полученное аудио
                playAudioBuffer(audioBuffer);
                
                // В реальном приложении здесь можно добавить 
                // обработку текста ответа от сервера
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
                const reader = response.body.getReader();
                const chunks = [];
                
                // Читаем стрим ответа
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    chunks.push(value);
                }
                
                // Собираем все части в один ArrayBuffer
                const totalLength = chunks.reduce((acc, val) => acc + val.length, 0);
                const audioData = new Uint8Array(totalLength);
                let offset = 0;
                for (const chunk of chunks) {
                    audioData.set(chunk, offset);
                    offset += chunk.length;
                }
                
                // Преобразуем в Int16Array для воспроизведения
                const audioBuffer = new Int16Array(audioData.buffer);
                
                // Воспроизводим аудио
                playAudioBuffer(audioBuffer);
            } else {
                statusElement.textContent = 'Ошибка при отправке аудио';
            }
        } catch (error) {
            console.error('Ошибка при отправке аудио:', error);
            statusElement.textContent = 'Ошибка при отправке аудио';
        }
    }
}); 