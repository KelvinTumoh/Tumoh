// ============================================================
// CHAT UI - COMPLETE WORKING VERSION
// ============================================================

let ws = null;
let currentRoomId = 'General';
let userId = 'user_' + Date.now();
let messageCounter = 0;
let isConnecting = false;

// DOM Elements with fallback creation
(function cleanupNestedChatMessages() {
    const container = document.getElementById('chat-messages');
    if (container) {
        const nested = container.querySelector('#chat-messages');
        if (nested) {
            console.log('Cleaning nested chat-messages...');
            while (nested.firstChild) {
                container.appendChild(nested.firstChild);
            }
            nested.remove();
            console.log('Nested chat-messages removed');
        }
    }
})();

let chatMessages = document.getElementById('chat-messages');
let chatInput = document.getElementById('chat-input');
let sendBtn = document.getElementById('send-btn');
let voiceBtn = document.getElementById('voice-btn');
let imageBtn = document.getElementById('image-btn');
let pdfBtn = document.getElementById('pdf-btn');
let roomSelector = document.getElementById('room-selector');
let connectionStatus = document.getElementById('connection-status');

// If chatMessages doesn't exist, create it
if (!chatMessages) {
    console.warn('⚠️ chat-messages not found - creating dynamically');
    chatMessages = document.createElement('div');
    chatMessages.id = 'chat-messages';
    chatMessages.style.cssText = 'flex:1; overflow-y:auto; padding:10px; background:#1e1e2e; min-height:200px; color:#cdd6f4;';
    const chatSection = document.getElementById('chat-section');
    if (chatSection) {
        chatSection.appendChild(chatMessages);
    } else {
        document.body.appendChild(chatMessages);
    }
}

// ============================================================
// WebSocket Connection
// ============================================================

function connectWebSocket() {
    if (isConnecting) return;
    isConnecting = true;
    
    const wsUrl = 'ws://localhost:8765';
    console.log('🔌 Connecting to:', wsUrl);
    
    try {
        ws = new WebSocket(wsUrl);
    } catch (e) {
        console.error('❌ Failed to create WebSocket:', e);
        addSystemMessage('⚠️ Failed to connect. Please refresh.');
        isConnecting = false;
        return;
    }
    
    ws.onopen = function() {
        console.log('✅ WebSocket connected');
        isConnecting = false;
        updateConnectionStatus(true);
        addSystemMessage('Connected to chat');
        setTimeout(() => joinRoom('General'), 100);
    };
    
    ws.onmessage = function(event) {
        console.log('📥 Raw message:', event.data);
        
        try {
            const data = JSON.parse(event.data);
            console.log('📥 Parsed data:', data);
            
            // Handle errors
            if (data.type === 'error') {
                console.error('❌ Server error:', data);
                addSystemMessage('⚠️ ' + (data.message || data.content || 'Unknown error'));
                return;
            }
            
            // Handle presence
            if (data.type === 'presence') {
                console.log('👤 Presence update:', data);
                return;
            }
            
            // Handle diagnostics (LSP) - ignore
            if (data.type === 'diagnostics') {
                console.log('📊 Diagnostics received (ignored)');
                return;
            }
            
            // Handle chat messages (echo from server)
            if (data.type === 'chat') {
                const messageData = data.message || data;
                // Check if it's our own message (to avoid duplicate)
                if (messageData.sender_id === userId) {
                    console.log('⏭️ Skipping own echo');
                    return;
                }
                displayMessage(messageData);
                return;
            }
            
            // Handle system messages - THIS IS TUMOH'S RESPONSE!
            if (data.type === 'system' || data.sender === 'Tumoh' || data.sender === 'tumoh') {
                console.log('💕 Tumoh response received!');
                displayMessage({
                    sender: '💕 Tumoh',
                    content: data.content,
                    timestamp: data.timestamp,
                    type: 'system'
                });
                return;
            }
            
            // If it has content, display it anyway
            if (data.content) {
                displayMessage(data);
                return;
            }
            
            console.log('⚠️ Unknown message type:', data.type);
            
        } catch (e) {
            console.error('❌ Error parsing message:', e);
            console.error('Raw data:', event.data);
        }
    };
    
    ws.onerror = function(error) {
        console.error('❌ WebSocket error:', error);
        isConnecting = false;
        updateConnectionStatus(false);
        addSystemMessage('⚠️ Connection error. Please refresh.');
    };
    
    ws.onclose = function() {
        console.log('🔌 WebSocket disconnected');
        isConnecting = false;
        updateConnectionStatus(false);
        addSystemMessage('Disconnected from chat');
        setTimeout(() => {
            console.log('🔄 Attempting to reconnect...');
            connectWebSocket();
        }, 3000);
    };
}

function updateConnectionStatus(connected) {
    if (connectionStatus) {
        connectionStatus.textContent = connected ? '🟢 Connected' : '🔴 Disconnected';
        connectionStatus.style.color = connected ? '#a6e3a1' : '#f38ba8';
    }
}

// ============================================================
// Room Management
// ============================================================

function joinRoom(roomName) {
    currentRoomId = roomName;
    if (chatMessages) chatMessages.innerHTML = '';
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'presence',
            room_id: roomName,
            user_id: userId,
            action: 'join'
        }));
    }
    addSystemMessage('Switched to room: ' + roomName);
}

// ============================================================
// Sending Messages
// ============================================================

function sendMessage() {
    if (!chatInput) {
        console.error('❌ Chat input not found');
        return;
    }
    
    const text = chatInput.value.trim();
    if (!text) return;
    
    chatInput.value = '';
    console.log('📨 Sending message:', text);
    
    displayMessage({
        sender: 'You',
        content: text,
        timestamp: new Date().toISOString(),
        id: 'local_' + Date.now()
    });
    
    const message = {
        type: 'chat',
        room_id: currentRoomId || 'General',
        user_id: userId,
        message: {
            id: 'msg_' + Date.now() + '_' + (++messageCounter),
            content: text,
            timestamp: new Date().toISOString(),
            sender: userId
        }
    };
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(message));
        console.log('✅ Message sent to server');
    } else {
        console.error('❌ WebSocket not open');
        addSystemMessage('⚠️ Connection lost. Please refresh.');
        connectWebSocket();
    }
}

// ============================================================
// Display Functions
// ============================================================

function displayMessage(message) {
    if (!chatMessages) {
        chatMessages = document.getElementById('chat-messages');
        if (!chatMessages) {
            console.error('❌ Cannot find chat container');
            return;
        }
    }
    
    if (message.id) {
        const existing = chatMessages.querySelector(`[data-message-id="${message.id}"]`);
        if (existing) {
            console.log('⏭️ Skipping duplicate:', message.id);
            return;
        }
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    if (message.id) messageDiv.setAttribute('data-message-id', message.id);
    
    const sender = message.sender || message.sender_name || 'Unknown';
    const isTumoh = sender.toLowerCase() === 'tumoh' || sender.toLowerCase() === 'system' || message.type === 'system';
    const isUser = sender.toLowerCase() === 'you' || sender === userId || (!isTumoh && message.type !== 'system');
    
    let displayName = isTumoh ? '💕 Tumoh' : (isUser ? 'You' : sender);
    let displayClass = isTumoh ? 'system-message' : (isUser ? 'user-message' : 'other-message');
    
    const timeStr = formatTime(message.timestamp);
    const content = message.content || message.text || '';
    
    messageDiv.className = `message ${displayClass}`;
    messageDiv.innerHTML = `
        <div class="message-content">
            <span class="sender">${displayName}</span>
            <span class="text">${content}</span>
            ${timeStr ? `<span class="time">${timeStr}</span>` : ''}
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemMessage(text) {
    if (!chatMessages) return;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system-message';
    messageDiv.innerHTML = `
        <div class="message-content system">
            <span class="sender">📢 System</span>
            <span class="text">${text}</span>
            <span class="time">${new Date().toLocaleTimeString()}</span>
        </div>
    `;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatTime(timestamp) {
    if (!timestamp) return '';
    try { return new Date(timestamp).toLocaleTimeString(); } catch (e) { return ''; }
}

// ============================================================
// Event Listeners
// ============================================================

if (sendBtn) sendBtn.addEventListener('click', sendMessage);
if (chatInput) {
    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}
if (roomSelector) {
    roomSelector.addEventListener('change', function() {
        if (this.value) joinRoom(this.value);
    });
}
if (voiceBtn) voiceBtn.addEventListener('click', () => addSystemMessage('🎙️ Voice input coming soon!'));
if (imageBtn) imageBtn.addEventListener('click', () => addSystemMessage('🖼️ Image upload coming soon!'));
if (pdfBtn) pdfBtn.addEventListener('click', () => addSystemMessage('📄 PDF upload coming soon!'));

// ============================================================
// Initialize
// ============================================================

console.log('🚀 Chat UI initializing...');
connectWebSocket();

window.sendMessage = sendMessage;
window.joinRoom = joinRoom;
window.debug = { ws, userId, currentRoomId, chatMessages };

console.log('✅ Chat UI initialized');
console.log('💡 Type "sendMessage()" in console to test');

// ============================================================
// FIX: Ensure event listeners are properly attached
// ============================================================

console.log('🔧 Setting up event listeners...');

// Refresh references to the live elements
chatInput = document.getElementById('chat-input');
sendBtn = document.getElementById('send-btn');

console.log('📋 Chat input found:', !!chatInput);
console.log('📋 Send button found:', !!sendBtn);

// Send on button click
if (sendBtn) {
    const newSendBtn = sendBtn.cloneNode(true);
    sendBtn.parentNode.replaceChild(newSendBtn, sendBtn);
    sendBtn = newSendBtn;
    newSendBtn.addEventListener('click', function(e) {
        console.log('🖱️ Send button clicked!');
        sendMessage();
        e.stopImmediatePropagation();
    });
    console.log('✅ Send button listener attached');
} else {
    console.error('❌ Send button not found!');
}

// Send on Enter key
if (chatInput) {
    const newInput = chatInput.cloneNode(true);
    chatInput.parentNode.replaceChild(newInput, chatInput);
    chatInput = newInput;
    newInput.addEventListener('keydown', function(e) {
        console.log('⌨️ Key pressed:', e.key);
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            console.log('✅ Enter pressed - sending!');
            sendMessage();
        }
    });
    console.log('✅ Chat input listener attached');
} else {
    console.error('❌ Chat input not found!');
}

// Also add a global click handler as fallback
document.addEventListener('click', function(e) {
    if (e.target.id === 'send-btn' || e.target.closest('#send-btn')) {
        console.log('🖱️ Send button clicked (global fallback)');
        sendMessage();
    }
});

console.log('✅ Event listeners setup complete');
