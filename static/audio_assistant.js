
// Continuous Audio Streaming for Wake Word Detection
const SAMPLE_RATE = 44100;
const BIT_DEPTH = 16;
const CHANNELS = 2;
const LISTENING_CHUNK_MS = 2000;  // 2 seconds for wake word detection
const COMMAND_CHUNK_MS = 6000;     // 6 seconds for command capture

let audioContext;
let scriptProcessor;
let audioChunks = [];
let isStreamingAudio = false;
let audioStream;
let audioSocket = null;
let chunkInterval = null;
let currentChunkDuration = LISTENING_CHUNK_MS;  // Start with listening duration

async function startContinuousListening() {
    try {
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const btn = document.getElementById('mic-btn');
        btn.textContent = "LISTENING";
        btn.style.backgroundColor = "#00f3ff";
        document.getElementById('voice-panel').classList.add('voice-active');
        document.getElementById('last-cmd').textContent = "Initializing...";

        // Create WebSocket connection for audio streaming
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Ensure charId is available globally from sheet.html
        if (typeof charId === 'undefined') {
            console.error("charId is not defined. Cannot connect to audio websocket.");
            return;
        }
        const audioWsUrl = `${protocol}//${window.location.host}/ws/audio/${charId}`;
        audioSocket = new WebSocket(audioWsUrl);

        audioSocket.onopen = () => {
            console.log("Audio WebSocket connected");
            document.getElementById('last-cmd').textContent = "Listening for 'Gibson'...";
        };

        audioSocket.onmessage = (event) => {
            const msg = JSON.parse(event.data);

            if (msg.type === 'state') {
                document.getElementById('last-cmd').textContent = msg.message;

                if (msg.state === 'wake_word_detected') {
                    const btn = document.getElementById('mic-btn');
                    btn.style.backgroundColor = "#ff0055";
                    btn.textContent = "COMMAND";

                    // Switch to longer chunk duration for command capture
                    currentChunkDuration = COMMAND_CHUNK_MS;
                    restartChunkInterval();
                } else if (msg.state === 'listening') {
                    const btn = document.getElementById('mic-btn');
                    btn.style.backgroundColor = "#00f3ff";
                    btn.textContent = "LISTENING";

                    // Switch back to shorter chunk duration for wake word
                    currentChunkDuration = LISTENING_CHUNK_MS;
                    restartChunkInterval();
                }
            } else if (msg.type === 'command_received') {
                document.getElementById('last-cmd').textContent = `Command: "${msg.text}"`;
            } else if (msg.type === 'command_processed') {
                console.log("Command processed:", msg.response);
            } else if (msg.type === 'error') {
                console.error("Audio stream error:", msg.message);
            }
        };

        audioSocket.onerror = (error) => {
            console.error("Audio WebSocket error:", error);
            document.getElementById('last-cmd').textContent = "Connection error";
        };

        audioSocket.onclose = () => {
            console.log("Audio WebSocket closed");
            if (isStreamingAudio) {
                document.getElementById('last-cmd').textContent = "Connection lost";
            }
        };

        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        await audioContext.resume();

        scriptProcessor = audioContext.createScriptProcessor(4096, CHANNELS, CHANNELS);
        const source = audioContext.createMediaStreamSource(audioStream);
        source.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);

        scriptProcessor.onaudioprocess = (e) => {
            if (!isStreamingAudio) return;

            const inputData = e.inputBuffer.getChannelData(0);
            const rightData = e.inputBuffer.getChannelData(1);

            const leftInt16 = convertFloatToInt16(inputData);
            const rightInt16 = convertFloatToInt16(rightData);

            // Properly interleave stereo: L,R,L,R,L,R...
            const interleaved = new Int16Array(inputData.length * 2);
            for (let i = 0; i < inputData.length; i++) {
                interleaved[i * 2] = leftInt16[i];
                interleaved[i * 2 + 1] = rightInt16[i];
            }

            audioChunks.push(interleaved);
        };

        isStreamingAudio = true;

        // Send audio chunks - starts with listening duration
        startChunkInterval();

    } catch (err) {
        console.error("Error starting continuous listening:", err);
        document.getElementById('last-cmd').textContent = "Mic Error: " + err.message;
    }
}

function startChunkInterval() {
    chunkInterval = setInterval(() => {
        if (audioChunks.length > 0 && audioSocket && audioSocket.readyState === WebSocket.OPEN) {
            // Combine chunks
            const totalLength = audioChunks.reduce((acc, chunk) => acc + chunk.length, 0);
            const buffer = new Int16Array(totalLength);
            let offset = 0;
            for (const chunk of audioChunks) {
                buffer.set(chunk, offset);
                offset += chunk.length;
            }

            // Create WAV
            const wavBlob = createWavBlob(buffer, SAMPLE_RATE);

            // Send via WebSocket as binary
            wavBlob.arrayBuffer().then(arrayBuffer => {
                audioSocket.send(arrayBuffer);
            });

            // Clear chunks
            audioChunks = [];
        }
    }, currentChunkDuration);
}

function restartChunkInterval() {
    if (chunkInterval) {
        clearInterval(chunkInterval);
        chunkInterval = null;
    }
    startChunkInterval();
}

async function stopContinuousListening() {
    isStreamingAudio = false;

    if (chunkInterval) {
        clearInterval(chunkInterval);
    }

    if (audioStream) {
        audioStream.getTracks().forEach((track) => track.stop());
    }

    if (scriptProcessor) {
        scriptProcessor.disconnect();
    }

    if (audioContext) {
        await audioContext.close();
    }

    if (audioSocket) {
        audioSocket.close();
        audioSocket = null;
    }

    const btn = document.getElementById('mic-btn');
    if (btn) {
        btn.textContent = "OFF";
        btn.style.backgroundColor = "#222";
    }
    const panel = document.getElementById('voice-panel');
    if (panel) panel.classList.remove('voice-active');

    const cmd = document.getElementById('last-cmd');
    if (cmd) cmd.textContent = "";

    audioChunks = [];
}

function convertFloatToInt16(float32Array) {
    const l = float32Array.length;
    const int16Array = new Int16Array(l);
    for (let i = 0; i < l; i++) {
        const s = Math.max(-1, Math.min(1, float32Array[i]));
        int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return int16Array;
}

function createWavBlob(buffer, sampleRate) {
    const numChannels = CHANNELS;
    const byteRate = sampleRate * numChannels * (BIT_DEPTH / 8);
    const blockAlign = numChannels * (BIT_DEPTH / 8);

    const header = new ArrayBuffer(44);
    const view = new DataView(header);

    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + buffer.byteLength, true); // Use byteLength, not length
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, BIT_DEPTH, true);
    writeString(view, 36, "data");
    view.setUint32(40, buffer.byteLength, true); // Use byteLength, not length

    const wavData = new Uint8Array(header);
    const finalBuffer = new Uint8Array(header.byteLength + buffer.byteLength);
    finalBuffer.set(wavData, 0);
    finalBuffer.set(new Uint8Array(buffer.buffer), wavData.byteLength);

    return new Blob([finalBuffer], { type: "audio/wav" });
}

function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

async function uploadAndTranscribe(blob) {
    const formData = new FormData();
    formData.append("audio", blob, "recording.wav");

    try {
        const response = await fetch("/api/transcribe", {
            method: "POST",
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            const transcript = data.text || "";

            document.getElementById('last-cmd').textContent = transcript || "(no speech detected)";

            if (transcript && socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: 'command', text: transcript }));
            }
        } else {
            const error = await response.text();
            document.getElementById('last-cmd').textContent = "Transcription failed";
            console.error("Transcription error:", error);
        }
    } catch (error) {
        document.getElementById('last-cmd').textContent = "Upload error";
        console.error("Upload error:", error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const micBtn = document.getElementById('mic-btn');
    if (micBtn) {
        micBtn.addEventListener('click', async () => {
            if (!isStreamingAudio) {
                await startContinuousListening();
            } else {
                await stopContinuousListening();
            }
        });
    }
});
