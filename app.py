from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import datetime
import uuid
import json
import base64
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=50000000)

# Хранилища данных
users = {}
servers = {
    'main': {
        'name': 'VoxCord Server',
        'channels': {
            'general': {'type': 'text', 'messages': [], 'users': []},
            'gaming': {'type': 'text', 'messages': [], 'users': []},
            'music': {'type': 'text', 'messages': [], 'users': []},
            'memes': {'type': 'text', 'messages': [], 'users': []},
        },
        'voice_channels': {
            'General Voice': {'users': [], 'connections': []},
            'Gaming Voice': {'users': [], 'connections': []},
            'Music Room': {'users': [], 'connections': []},
        },
        'roles': ['@everyone', 'Admin', 'Moderator', 'VIP'],
        'members': {}
    }
}
screen_shares = {}  # Для демонстрации экрана

class User:
    def __init__(self, username, sid):
        self.id = str(uuid.uuid4())[:8]
        self.username = username
        self.sid = sid
        self.avatar_url = None
        self.status = 'online'
        self.current_server = 'main'
        self.current_channel = 'general'
        self.voice_channel = None
        self.is_muted = False
        self.is_deafened = False
        self.is_streaming = False
        self.roles = ['@everyone']
        self.bio = ''
        self.color = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7', 
                      '#a29bfe', '#fd79a8', '#00b894', '#e17055', '#6c5ce7'][len(users) % 10]

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VoxCord - Discord Clone</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-primary: #313338;
            --bg-secondary: #2b2d31;
            --bg-tertiary: #1e1f22;
            --bg-hover: #35373c;
            --text-primary: #ffffff;
            --text-secondary: #b5bac1;
            --text-muted: #80848e;
            --blurple: #5865f2;
            --green: #3ba55c;
            --red: #ed4245;
            --yellow: #faa81a;
            --server-size: 72px;
            --sidebar-width: 240px;
            --members-width: 240px;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            overflow: hidden;
            user-select: none;
        }
        
        /* Экран логина */
        .login-screen {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            position: relative;
            overflow: hidden;
        }
        .login-screen::before {
            content: '';
            position: absolute;
            width: 200%;
            height: 200%;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="1" fill="white" opacity="0.1"/></svg>');
            animation: float 20s linear infinite;
        }
        @keyframes float {
            0% { transform: translate(0, 0) rotate(0deg); }
            100% { transform: translate(-50%, -50%) rotate(360deg); }
        }
        .login-box {
            background: var(--bg-primary);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            width: 480px;
            position: relative;
            z-index: 1;
        }
        .login-logo {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-logo i {
            font-size: 56px;
            color: var(--blurple);
            margin-bottom: 15px;
        }
        .login-logo h1 {
            font-size: 28px;
            font-weight: 700;
        }
        .login-logo p {
            color: var(--text-secondary);
            font-size: 14px;
            margin-top: 8px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .form-group input {
            width: 100%;
            padding: 12px 16px;
            background: var(--bg-tertiary);
            border: 2px solid transparent;
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 16px;
            transition: border-color 0.3s;
        }
        .form-group input:focus {
            outline: none;
            border-color: var(--blurple);
        }
        .login-btn {
            width: 100%;
            padding: 14px;
            background: var(--blurple);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        .login-btn:hover { background: #4752c4; transform: translateY(-2px); }
        .login-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .connection-status {
            text-align: center;
            margin-top: 15px;
            font-size: 13px;
        }
        .connection-status.connected { color: var(--green); }
        .connection-status.error { color: var(--red); }
        .connection-status.connecting { color: var(--yellow); }
        
        /* Основной интерфейс */
        .app { display: none; height: 100vh; }
        .app.active { display: flex; }
        
        /* Панель серверов */
        .servers-bar {
            width: var(--server-size);
            background: var(--bg-tertiary);
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 12px 0;
            gap: 8px;
            overflow-y: auto;
        }
        .server-icon {
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: var(--bg-primary);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
            flex-shrink: 0;
        }
        .server-icon:hover, .server-icon.active {
            border-radius: 16px;
            background: var(--blurple);
        }
        .server-icon.active::before {
            content: '';
            position: absolute;
            left: -16px;
            width: 4px;
            height: 40px;
            background: white;
            border-radius: 0 4px 4px 0;
        }
        .server-separator {
            width: 32px;
            height: 2px;
            background: var(--bg-hover);
            border-radius: 1px;
        }
        .add-server {
            border: 2px dashed var(--green);
            color: var(--green);
            font-size: 20px;
        }
        .add-server:hover {
            background: var(--green) !important;
            color: white;
        }
        
        /* Боковая панель каналов */
        .channels-sidebar {
            width: var(--sidebar-width);
            background: var(--bg-secondary);
            display: flex;
            flex-direction: column;
            min-width: var(--sidebar-width);
        }
        .server-header {
            padding: 16px;
            border-bottom: 1px solid var(--bg-tertiary);
            font-weight: 700;
            font-size: 15px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
        }
        .server-header:hover { background: var(--bg-hover); }
        
        .channels-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }
        .channel-category {
            margin-bottom: 16px;
        }
        .category-header {
            display: flex;
            align-items: center;
            padding: 8px;
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            cursor: pointer;
            gap: 4px;
        }
        .category-header:hover { color: var(--text-secondary); }
        .category-header i { font-size: 8px; }
        
        .channel {
            display: flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            color: var(--text-muted);
            margin: 1px 0;
            font-size: 14px;
            gap: 8px;
            transition: all 0.15s;
        }
        .channel:hover { background: var(--bg-hover); color: var(--text-primary); }
        .channel.active { background: var(--bg-hover); color: var(--text-primary); }
        .channel i { width: 20px; text-align: center; }
        
        .voice-channel-item {
            display: flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            color: var(--text-muted);
            margin: 1px 0;
            font-size: 14px;
            gap: 8px;
            transition: all 0.15s;
        }
        .voice-channel-item:hover { background: var(--bg-hover); color: var(--text-primary); }
        .voice-channel-item.active { background: var(--green); color: white; }
        .voice-channel-item .user-count {
            margin-left: auto;
            background: var(--bg-tertiary);
            padding: 2px 6px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 600;
        }
        
        /* Профиль пользователя */
        .user-panel {
            padding: 8px;
            background: var(--bg-tertiary);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .user-avatar-small {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
            position: relative;
            flex-shrink: 0;
        }
        .user-avatar-small .status-badge {
            position: absolute;
            bottom: 0;
            right: 0;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            border: 3px solid var(--bg-tertiary);
        }
        .status-badge.online { background: var(--green); }
        .status-badge.idle { background: var(--yellow); }
        .status-badge.dnd { background: var(--red); }
        .status-badge.offline { background: #747f8d; }
        
        .user-info-mini {
            flex: 1;
            min-width: 0;
        }
        .user-info-mini .username {
            font-size: 13px;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .user-info-mini .userid {
            font-size: 11px;
            color: var(--text-muted);
        }
        .user-controls {
            display: flex;
            gap: 2px;
        }
        .user-control-btn {
            width: 28px;
            height: 28px;
            border-radius: 4px;
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s;
        }
        .user-control-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
        .user-control-btn.active { color: var(--red); }
        
        /* Область чата */
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg-primary);
            min-width: 0;
        }
        .chat-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--bg-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 600;
            font-size: 15px;
        }
        .chat-header i { color: var(--text-muted); }
        
        .chat-toolbar {
            display: flex;
            gap: 8px;
            margin-left: auto;
        }
        .toolbar-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            padding: 6px;
            border-radius: 4px;
            font-size: 14px;
            transition: all 0.15s;
        }
        .toolbar-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
        
        .messages-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }
        
        .message-group {
            margin-bottom: 16px;
        }
        .message {
            display: flex;
            gap: 12px;
            padding: 2px 16px;
            margin: 1px 0;
            transition: background 0.15s;
        }
        .message:hover { background: var(--bg-hover); }
        .message-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 18px;
            flex-shrink: 0;
            cursor: pointer;
        }
        .message-content { flex: 1; min-width: 0; }
        .message-header {
            display: flex;
            align-items: baseline;
            gap: 8px;
            margin-bottom: 2px;
        }
        .message-username {
            font-weight: 600;
            font-size: 15px;
            cursor: pointer;
        }
        .message-username:hover { text-decoration: underline; }
        .message-badge {
            font-size: 10px;
            font-weight: 700;
            padding: 1px 5px;
            border-radius: 3px;
            background: var(--blurple);
            color: white;
            text-transform: uppercase;
        }
        .message-time {
            font-size: 11px;
            color: var(--text-muted);
        }
        .message-text {
            color: var(--text-primary);
            line-height: 1.5;
            word-wrap: break-word;
            font-size: 15px;
        }
        .message-text img {
            max-width: 300px;
            border-radius: 8px;
            margin-top: 8px;
        }
        
        /* Поле ввода */
        .chat-input-area {
            padding: 0 16px 16px;
        }
        .chat-input-wrapper {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 0 16px;
        }
        .chat-input-tools {
            display: flex;
            gap: 4px;
            padding: 8px 0;
        }
        .input-tool-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 18px;
            transition: all 0.15s;
            position: relative;
        }
        .input-tool-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
        .input-tool-btn input[type="file"] {
            position: absolute;
            opacity: 0;
            width: 100%;
            height: 100%;
            cursor: pointer;
        }
        .chat-input-main {
            display: flex;
            align-items: center;
            gap: 8px;
            padding-bottom: 8px;
        }
        .chat-input-main textarea {
            flex: 1;
            background: none;
            border: none;
            color: var(--text-primary);
            font-size: 15px;
            font-family: inherit;
            resize: none;
            outline: none;
            min-height: 24px;
            max-height: 200px;
            padding: 4px 0;
            line-height: 1.4;
        }
        .chat-input-main textarea::placeholder { color: var(--text-muted); }
        
        .emoji-picker-btn, .send-message-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            font-size: 18px;
            transition: all 0.15s;
        }
        .emoji-picker-btn:hover, .send-message-btn:hover { color: var(--text-primary); }
        
        /* Панель участников */
        .members-panel {
            width: var(--members-width);
            background: var(--bg-secondary);
            padding: 16px;
            overflow-y: auto;
            min-width: var(--members-width);
        }
        .members-title {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }
        .member-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: background 0.15s;
        }
        .member-item:hover { background: var(--bg-hover); }
        .member-avatar-small {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 14px;
            flex-shrink: 0;
            position: relative;
        }
        .member-name {
            font-size: 14px;
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .member-role {
            font-size: 10px;
            color: var(--text-muted);
            margin-left: auto;
        }
        
        /* Панель голосового чата */
        .voice-panel {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--bg-primary);
            border-radius: 12px;
            padding: 16px;
            min-width: 320px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.6);
            display: none;
            z-index: 1000;
            border: 1px solid var(--bg-hover);
        }
        .voice-panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--bg-hover);
        }
        .voice-panel-header h3 { font-size: 15px; }
        .voice-connection-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: var(--green);
        }
        .voice-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--green);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .voice-participants-list {
            max-height: 200px;
            overflow-y: auto;
            margin-bottom: 12px;
        }
        .voice-participant-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px;
            background: var(--bg-secondary);
            border-radius: 6px;
            margin-bottom: 4px;
        }
        .voice-controls-row {
            display: flex;
            gap: 8px;
        }
        .voice-control-btn {
            flex: 1;
            padding: 10px;
            background: var(--bg-secondary);
            border: none;
            border-radius: 6px;
            color: var(--text-primary);
            cursor: pointer;
            text-align: center;
            font-size: 13px;
            transition: all 0.15s;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }
        .voice-control-btn:hover { background: var(--bg-hover); }
        .voice-control-btn.active { background: var(--blurple); }
        .voice-control-btn.danger { background: var(--red); }
        .voice-control-btn.stream { background: #9146FF; }
        
        /* Модальное окно стрима */
        .stream-modal {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: var(--bg-primary);
            border-radius: 12px;
            padding: 20px;
            min-width: 600px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.8);
            display: none;
            z-index: 2000;
        }
        .stream-modal video {
            width: 100%;
            border-radius: 8px;
            margin: 10px 0;
        }
        .stream-controls {
            display: flex;
            gap: 8px;
            margin-top: 10px;
        }
        
        /* Скроллбар */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--bg-tertiary); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--bg-hover); }
        
        /* Адаптивность */
        @media (max-width: 1024px) {
            .members-panel { display: none; }
        }
        @media (max-width: 768px) {
            .servers-bar { display: none; }
            .channels-sidebar { width: 200px; min-width: 200px; }
        }
    </style>
</head>
<body>
    <!-- Экран входа -->
    <div id="loginScreen" class="login-screen">
        <div class="login-box">
            <div class="login-logo">
                <i class="fab fa-discord"></i>
                <h1>VoxCord</h1>
                <p>Общайтесь, стримьте и будьте вместе</p>
            </div>
            <div class="form-group">
                <label>Имя пользователя</label>
                <input type="text" id="usernameInput" placeholder="Как вас зовут?" maxlength="32" autocomplete="off">
            </div>
            <button class="login-btn" id="loginBtn" onclick="login()">
                <i class="fas fa-sign-in-alt"></i> Присоединиться
            </button>
            <div class="connection-status connecting" id="connStatus">
                <i class="fas fa-circle-notch fa-spin"></i> Подключение к серверу...
            </div>
        </div>
    </div>

    <!-- Главный интерфейс -->
    <div id="appScreen" class="app">
        <!-- Серверы -->
        <div class="servers-bar">
            <div class="server-icon active" title="VoxCord">
                <i class="fab fa-discord" style="font-size: 24px;"></i>
            </div>
            <div class="server-separator"></div>
            <div class="server-icon add-server" title="Добавить сервер">
                <i class="fas fa-plus"></i>
            </div>
            <div class="server-icon" title="Исследовать серверы">
                <i class="fas fa-compass"></i>
            </div>
        </div>

        <!-- Каналы -->
        <div class="channels-sidebar">
            <div class="server-header">
                <span>VoxCord Server</span>
                <i class="fas fa-chevron-down" style="font-size: 12px;"></i>
            </div>
            <div class="channels-scroll">
                <div class="channel-category">
                    <div class="category-header">
                        <i class="fas fa-chevron-down"></i>
                        ТЕКСТОВЫЕ КАНАЛЫ
                        <i class="fas fa-plus" style="margin-left: auto; cursor: pointer;" title="Создать канал"></i>
                    </div>
                    <div class="channel active" data-channel="general">
                        <i class="fas fa-hashtag"></i> general
                    </div>
                    <div class="channel" data-channel="gaming">
                        <i class="fas fa-hashtag"></i> gaming
                    </div>
                    <div class="channel" data-channel="music">
                        <i class="fas fa-hashtag"></i> music
                    </div>
                    <div class="channel" data-channel="memes">
                        <i class="fas fa-hashtag"></i> memes
                    </div>
                </div>
                
                <div class="channel-category">
                    <div class="category-header">
                        <i class="fas fa-chevron-down"></i>
                        ГОЛОСОВЫЕ КАНАЛЫ
                        <i class="fas fa-plus" style="margin-left: auto; cursor: pointer;" title="Создать канал"></i>
                    </div>
                    <div class="voice-channel-item" data-voice="General Voice">
                        <i class="fas fa-volume-up"></i> General Voice
                        <span class="user-count">0</span>
                    </div>
                    <div class="voice-channel-item" data-voice="Gaming Voice">
                        <i class="fas fa-volume-up"></i> Gaming Voice
                        <span class="user-count">0</span>
                    </div>
                    <div class="voice-channel-item" data-voice="Music Room">
                        <i class="fas fa-volume-up"></i> Music Room
                        <span class="user-count">0</span>
                    </div>
                </div>
            </div>
            
            <!-- Профиль -->
            <div class="user-panel">
                <div class="user-avatar-small" id="userAvatarSmall">
                    ?
                    <span class="status-badge online"></span>
                </div>
                <div class="user-info-mini">
                    <div class="username" id="userNameSmall">User</div>
                    <div class="userid" id="userIdSmall">#0000</div>
                </div>
                <div class="user-controls">
                    <button class="user-control-btn" id="muteBtn" onclick="toggleMute()" title="Выкл. микрофон">
                        <i class="fas fa-microphone"></i>
                    </button>
                    <button class="user-control-btn" id="deafenBtn" onclick="toggleDeaf()" title="Выкл. звук">
                        <i class="fas fa-headphones"></i>
                    </button>
                    <button class="user-control-btn" onclick="openSettings()" title="Настройки">
                        <i class="fas fa-cog"></i>
                    </button>
                </div>
            </div>
        </div>

        <!-- Чат -->
        <div class="chat-area">
            <div class="chat-header">
                <i class="fas fa-hashtag"></i>
                <span id="channelTitle">general</span>
                <div class="chat-toolbar">
                    <button class="toolbar-btn" title="Поиск"><i class="fas fa-search"></i></button>
                    <button class="toolbar-btn" title="Закрепленные"><i class="fas fa-thumbtack"></i></button>
                    <button class="toolbar-btn" title="Уведомления"><i class="fas fa-bell"></i></button>
                </div>
            </div>
            
            <div class="messages-container" id="messagesContainer">
                <div style="text-align: center; padding: 60px 20px;">
                    <div style="font-size: 64px; margin-bottom: 20px;">👋</div>
                    <h2>Добро пожаловать в #general!</h2>
                    <p style="color: var(--text-secondary); margin-top: 8px;">
                        Это начало канала. Отправьте сообщение, чтобы начать общение.
                    </p>
                </div>
            </div>
            
            <div class="chat-input-area">
                <div class="chat-input-wrapper">
                    <div class="chat-input-tools">
                        <label class="input-tool-btn" title="Прикрепить файл">
                            <i class="fas fa-plus-circle"></i>
                            <input type="file" id="fileInput" accept="image/*" onchange="uploadFile()" hidden>
                        </label>
                        <button class="input-tool-btn" title="Эмодзи" onclick="toggleEmoji()">
                            <i class="far fa-smile"></i>
                        </button>
                        <button class="input-tool-btn" title="GIF">
                            <i class="fas fa-gift"></i>
                        </button>
                    </div>
                    <div class="chat-input-main">
                        <textarea id="messageInput" placeholder="Напишите сообщение в #general" rows="1" maxlength="2000"></textarea>
                        <button class="send-message-btn" onclick="sendMessage()" title="Отправить">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Участники -->
        <div class="members-panel">
            <div class="members-title">УЧАСТНИКИ — <span id="memberCount">0</span></div>
            <div style="margin-bottom: 16px;">
                <div class="members-title" style="font-size: 10px; margin-bottom: 4px;">В СЕТИ</div>
                <div id="onlineMembers"></div>
            </div>
            <div>
                <div class="members-title" style="font-size: 10px; margin-bottom: 4px;">НЕ В СЕТИ</div>
                <div id="offlineMembers"></div>
            </div>
        </div>
    </div>

    <!-- Панель голосового чата -->
    <div class="voice-panel" id="voicePanel">
        <div class="voice-panel-header">
            <h3><i class="fas fa-volume-up"></i> <span id="voiceChannelTitle">Голосовой чат</span></h3>
            <div class="voice-connection-status">
                <span class="voice-dot"></span> Подключены
            </div>
            <button onclick="disconnectVoice()" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:18px;">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="voice-participants-list" id="voiceParticipants"></div>
        <div class="voice-controls-row">
            <button class="voice-control-btn" id="voiceMicBtn" onclick="toggleMute()">
                <i class="fas fa-microphone"></i> Микрофон
            </button>
            <button class="voice-control-btn" id="voiceDeafBtn" onclick="toggleDeaf()">
                <i class="fas fa-volume-up"></i> Звук
            </button>
            <button class="voice-control-btn stream" id="streamBtn" onclick="startScreenShare()">
                <i class="fas fa-desktop"></i> Стрим
            </button>
            <button class="voice-control-btn danger" onclick="disconnectVoice()">
                <i class="fas fa-phone-slash"></i> Откл.
            </button>
        </div>
    </div>

    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
        const socket = io(window.location.origin, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000
        });

        let currentUser = null;
        let currentChannel = 'general';
        let currentVoiceChannel = null;
        let localStream = null;
        let screenStream = null;
        let peerConnections = {};
        let isMuted = false;
        let isDeafened = false;
        let isStreaming = false;

        const rtcConfig = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                {
                    urls: 'turn:openrelay.metered.ca:80',
                    username: 'openrelayproject',
                    credential: 'openrelayproject'
                },
                {
                    urls: 'turn:openrelay.metered.ca:443',
                    username: 'openrelayproject',
                    credential: 'openrelayproject'
                }
            ]
        };

        // Подключение
        socket.on('connect', () => {
            document.getElementById('connStatus').innerHTML = '<i class="fas fa-check-circle"></i> Подключено! Войдите.';
            document.getElementById('connStatus').className = 'connection-status connected';
        });

        socket.on('disconnect', () => {
            document.getElementById('connStatus').innerHTML = '<i class="fas fa-exclamation-circle"></i> Соединение потеряно';
            document.getElementById('connStatus').className = 'connection-status error';
        });

        // Логин
        function login() {
            const username = document.getElementById('usernameInput').value.trim();
            if (username.length < 2) return alert('Имя должно быть от 2 символов!');
            
            document.getElementById('loginBtn').disabled = true;
            document.getElementById('loginBtn').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Вход...';
            socket.emit('register', { username });
        }

        socket.on('registered', (data) => {
            currentUser = data;
            document.getElementById('loginScreen').style.display = 'none';
            document.getElementById('appScreen').classList.add('active');
            
            document.getElementById('userNameSmall').textContent = data.username;
            document.getElementById('userIdSmall').textContent = '#' + data.user_id;
            document.getElementById('userAvatarSmall').style.background = data.color;
            document.getElementById('userAvatarSmall').innerHTML = data.username[0].toUpperCase() + '<span class="status-badge online"></span>';
            
            document.getElementById('messageInput').focus();
        });

        // Чат
        socket.on('room_history', (data) => {
            document.getElementById('messagesContainer').innerHTML = '';
            if (data.messages?.length) {
                data.messages.forEach(addMessage);
            }
            updateMembers(data.users);
            scrollChat();
        });

        socket.on('new_message', (msg) => {
            if (msg.room === currentChannel) {
                addMessage(msg);
                scrollChat();
            }
        });

        socket.on('user_joined', (data) => {
            if (data.room === currentChannel) updateMembers(data.users);
        });

        socket.on('user_left', (data) => {
            if (data.room === currentChannel) updateMembers(data.users);
        });

        function sendMessage() {
            const input = document.getElementById('messageInput');
            const text = input.value.trim();
            if (!text || !currentUser) return;
            
            socket.emit('send_message', { room: currentChannel, text, type: 'text' });
            input.value = '';
            input.style.height = 'auto';
        }

        function uploadFile() {
            const file = document.getElementById('fileInput').files[0];
            if (!file || !currentUser) return;
            
            const reader = new FileReader();
            reader.onload = (e) => {
                socket.emit('send_message', {
                    room: currentChannel,
                    text: e.target.result,
                    type: 'image',
                    filename: file.name
                });
            };
            reader.readAsDataURL(file);
        }

        function addMessage(msg) {
            const container = document.getElementById('messagesContainer');
            const div = document.createElement('div');
            div.className = 'message';
            
            let content = '';
            if (msg.type === 'image') {
                content = `<img src="${msg.text}" alt="${msg.filename}" style="max-width:400px;border-radius:8px;">`;
            } else {
                content = msg.text.replace(/\n/g, '<br>');
            }
            
            div.innerHTML = `
                <div class="message-avatar" style="background:${msg.color || '#5865f2'}">
                    ${(msg.username || '?')[0].toUpperCase()}
                </div>
                <div class="message-content">
                    <div class="message-header">
                        <span class="message-username" style="color:${msg.color || '#5865f2'}">${msg.username}</span>
                        ${msg.role ? `<span class="message-badge">${msg.role}</span>` : ''}
                        <span class="message-time">${msg.time}</span>
                    </div>
                    <div class="message-text">${content}</div>
                </div>
            `;
            container.appendChild(div);
        }

        function updateMembers(users) {
            if (!users) return;
            document.getElementById('onlineMembers').innerHTML = users.map(u => `
                <div class="member-item">
                    <div class="member-avatar-small" style="background:${u.color || '#5865f2'}">${u.username[0].toUpperCase()}</div>
                    <span class="member-name">${u.username}</span>
                    ${u.role ? `<span class="member-role">${u.role}</span>` : ''}
                </div>
            `).join('');
            document.getElementById('memberCount').textContent = users.length;
        }

        function scrollChat() {
            const container = document.getElementById('messagesContainer');
            setTimeout(() => container.scrollTop = container.scrollHeight, 50);
        }

        // Голосовой чат
        async function joinVoice(channel) {
            try {
                localStream = await navigator.mediaDevices.getUserMedia({
                    audio: { echoCancellation: true, noiseSuppression: true }
                });
                
                currentVoiceChannel = channel;
                socket.emit('voice_join', { channel });
                
                document.getElementById('voicePanel').style.display = 'block';
                document.getElementById('voiceChannelTitle').textContent = channel;
                document.getElementById('voiceParticipants').innerHTML = '';
                
                addVoiceUser({ username: currentUser.username, user_id: currentUser.user_id });
                
                document.querySelectorAll('.voice-channel-item').forEach(el => {
                    el.classList.toggle('active', el.dataset.voice === channel);
                });
            } catch (err) {
                alert('Разрешите доступ к микрофону!');
            }
        }

        async function startScreenShare() {
            try {
                screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
                isStreaming = true;
                document.getElementById('streamBtn').classList.add('active');
                
                // Отправляем скриншот каждые 100мс
                const video = document.createElement('video');
                video.srcObject = screenStream;
                video.play();
                
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                
                const sendFrame = () => {
                    if (!isStreaming) return;
                    canvas.width = video.videoWidth / 4;
                    canvas.height = video.videoHeight / 4;
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                    
                    socket.emit('screen_share', {
                        channel: currentVoiceChannel,
                        frame: canvas.toDataURL('image/jpeg', 0.3)
                    });
                    
                    setTimeout(sendFrame, 100);
                };
                
                sendFrame();
                
                screenStream.getVideoTracks()[0].onended = () => stopScreenShare();
            } catch (err) {
                alert('Не удалось начать трансляцию экрана');
            }
        }

        function stopScreenShare() {
            if (screenStream) {
                screenStream.getTracks().forEach(t => t.stop());
                screenStream = null;
            }
            isStreaming = false;
            document.getElementById('streamBtn').classList.remove('active');
        }

        socket.on('screen_share_frame', (data) => {
            // Показываем стрим в модальном окне
            let streamModal = document.getElementById('streamModal');
            if (!streamModal) {
                streamModal = document.createElement('div');
                streamModal.id = 'streamModal';
                streamModal.className = 'stream-modal';
                streamModal.innerHTML = `
                    <h3>📺 Трансляция экрана</h3>
                    <img id="streamImage" style="width:100%;border-radius:8px;">
                    <div class="stream-controls">
                        <button class="voice-control-btn" onclick="document.getElementById('streamModal').style.display='none'">
                            <i class="fas fa-times"></i> Закрыть
                        </button>
                    </div>
                `;
                document.body.appendChild(streamModal);
            }
            streamModal.style.display = 'block';
            document.getElementById('streamImage').src = data.frame;
        });

        // WebRTC для голоса
        socket.on('voice_user_joined', async (data) => {
            addVoiceUser(data);
            updateVoiceCount(data.channel, 1);
            
            if (currentVoiceChannel && data.user_id !== currentUser.user_id) {
                await createPeerConnection(data.user_id, true);
            }
        });

        socket.on('voice_user_left', (data) => {
            document.getElementById('vp-' + data.user_id)?.remove();
            updateVoiceCount(data.channel, -1);
            if (peerConnections[data.user_id]) {
                peerConnections[data.user_id].close();
                delete peerConnections[data.user_id];
            }
        });

        socket.on('webrtc_offer', async (data) => {
            const pc = await createPeerConnection(data.from_user, false);
            await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            socket.emit('webrtc_answer', { to_user: data.from_user, answer });
        });

        socket.on('webrtc_answer', async (data) => {
            const pc = peerConnections[data.from_user];
            if (pc) await pc.setRemoteDescription(new RTCSessionDescription(data.answer));
        });

        socket.on('webrtc_ice', async (data) => {
            const pc = peerConnections[data.from_user];
            if (pc && data.candidate) {
                await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
            }
        });

        async function createPeerConnection(userId, initiator) {
            if (peerConnections[userId]) peerConnections[userId].close();
            
            const pc = new RTCPeerConnection(rtcConfig);
            peerConnections[userId] = pc;
            
            if (localStream) localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
            if (screenStream) screenStream.getVideoTracks().forEach(t => pc.addTrack(t, screenStream));
            
            pc.onicecandidate = (e) => {
                if (e.candidate) socket.emit('webrtc_ice', { to_user: userId, candidate: e.candidate });
            };
            
            pc.ontrack = (e) => {
                const audio = document.createElement('audio');
                audio.srcObject = e.streams[0];
                audio.autoplay = true;
                audio.id = 'audio-' + userId;
                document.body.appendChild(audio);
            };
            
            if (initiator) {
                const offer = await pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: true });
                await pc.setLocalDescription(offer);
                socket.emit('webrtc_offer', { to_user: userId, offer });
            }
            
            return pc;
        }

        function addVoiceUser(data) {
            const container = document.getElementById('voiceParticipants');
            const div = document.createElement('div');
            div.className = 'voice-participant-item';
            div.id = 'vp-' + data.user_id;
            div.innerHTML = `
                <div class="member-avatar-small" style="background:${data.color || '#5865f2'}">${data.username[0].toUpperCase()}</div>
                <span>${data.username}</span>
                <i class="fas fa-microphone" style="margin-left:auto;color:var(--green);font-size:12px;"></i>
            `;
            container.appendChild(div);
        }

        function updateVoiceCount(channel, change) {
            document.querySelectorAll('.voice-channel-item').forEach(el => {
                if (el.dataset.voice === channel) {
                    const count = el.querySelector('.user-count');
                    count.textContent = Math.max(0, (parseInt(count.textContent) || 0) + change);
                }
            });
        }

        function disconnectVoice() {
            if (currentVoiceChannel) {
                socket.emit('voice_leave', { channel: currentVoiceChannel });
                Object.values(peerConnections).forEach(pc => pc.close());
                peerConnections = {};
                if (localStream) { localStream.getTracks().forEach(t => t.stop()); localStream = null; }
                stopScreenShare();
                document.querySelectorAll('audio').forEach(a => a.remove());
                document.getElementById('voicePanel').style.display = 'none';
                document.querySelectorAll('.voice-channel-item').forEach(el => el.classList.remove('active'));
                currentVoiceChannel = null;
            }
        }

        function toggleMute() {
            if (localStream) {
                isMuted = !isMuted;
                localStream.getAudioTracks().forEach(t => t.enabled = !isMuted);
                document.getElementById('muteBtn').classList.toggle('active', isMuted);
                document.getElementById('voiceMicBtn').classList.toggle('active', isMuted);
            }
        }

        function toggleDeaf() {
            isDeafened = !isDeafened;
            document.querySelectorAll('audio').forEach(a => a.muted = isDeafened);
            document.getElementById('deafenBtn').classList.toggle('active', isDeafened);
            document.getElementById('voiceDeafBtn').classList.toggle('active', isDeafened);
        }

        function toggleEmoji() {
            const emojis = ['😀','😂','😍','🎮','💻','🎵','🔥','👍','❤️','👋','🎉','🤖','🦊','🐱','🌟'];
            const picker = document.createElement('div');
            picker.style.cssText = 'position:fixed;bottom:120px;left:320px;background:#2b2d31;padding:10px;border-radius:8px;display:flex;gap:5px;flex-wrap:wrap;width:300px;z-index:999;';
            picker.innerHTML = emojis.map(e => `<span style="cursor:pointer;font-size:24px;" onclick="document.getElementById('messageInput').value+='${e}';this.parentElement.remove();">${e}</span>`).join('');
            document.body.appendChild(picker);
            setTimeout(() => picker.remove(), 5000);
        }

        // Обработчики каналов
        document.querySelectorAll('.channel').forEach(ch => {
            ch.addEventListener('click', function() {
                document.querySelectorAll('.channel').forEach(c => c.classList.remove('active'));
                this.classList.add('active');
                currentChannel = this.dataset.channel;
                document.getElementById('channelTitle').textContent = currentChannel;
                document.getElementById('messageInput').placeholder = 'Напишите в #' + currentChannel;
                socket.emit('switch_channel', { channel: currentChannel });
            });
        });

        document.querySelectorAll('.voice-channel-item').forEach(ch => {
            ch.addEventListener('click', function() {
                const vc = this.dataset.voice;
                if (currentVoiceChannel === vc) {
                    disconnectVoice();
                } else {
                    if (currentVoiceChannel) disconnectVoice();
                    joinVoice(vc);
                }
            });
        });

        document.getElementById('messageInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        document.getElementById('usernameInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') login();
        });

        // Авто-ресайз textarea
        document.getElementById('messageInput').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 200) + 'px';
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

# Socket события
@socketio.on('connect')
def handle_connect():
    print(f'✅ {request.sid} подключен')

@socketio.on('disconnect')
def handle_disconnect():
    user = users.pop(request.sid, None)
    if user:
        for ch_name, ch_data in servers['main']['channels'].items():
            if user.username in ch_data['users']:
                ch_data['users'].remove(user.username)
                socketio.emit('user_left', {
                    'username': user.username,
                    'room': ch_name,
                    'users': [{'username': u.username, 'color': u.color, 'role': u.roles[-1] if len(u.roles) > 1 else None} 
                             for u in users.values() if u.current_channel == ch_name]
                }, room=ch_name)
        if user.voice_channel:
            handle_voice_leave({'channel': user.voice_channel})

@socketio.on('register')
def handle_register(data):
    username = data.get('username', '').strip()
    if len(username) < 2:
        socketio.emit('error', {'message': 'Имя слишком короткое'}, room=request.sid)
        return
    
    for u in users.values():
        if u.username.lower() == username.lower():
            socketio.emit('error', {'message': 'Имя занято'}, room=request.sid)
            return
    
    user = User(username, request.sid)
    users[request.sid] = user
    servers['main']['members'][user.id] = user
    
    join_room('general')
    servers['main']['channels']['general']['users'].append(user.username)
    
    socketio.emit('registered', {
        'user_id': user.id,
        'username': username,
        'color': user.color,
        'roles': user.roles
    }, room=request.sid)
    
    socketio.emit('room_history', {
        'room': 'general',
        'messages': servers['main']['channels']['general']['messages'][-50:],
        'users': [{'username': u.username, 'color': u.color, 'role': u.roles[-1] if len(u.roles) > 1 else None}
                  for u in users.values() if u.current_channel == 'general']
    }, room=request.sid)
    
    socketio.emit('user_joined', {
        'username': username,
        'room': 'general',
        'users': [{'username': u.username, 'color': u.color, 'role': u.roles[-1] if len(u.roles) > 1 else None}
                  for u in users.values() if u.current_channel == 'general']
    }, room='general')

@socketio.on('switch_channel')
def handle_switch(data):
    user = users.get(request.sid)
    if not user: return
    
    new_ch = data.get('channel', 'general')
    
    if user.current_channel in servers['main']['channels']:
        ch = servers['main']['channels'][user.current_channel]
        if user.username in ch['users']:
            ch['users'].remove(user.username)
            leave_room(user.current_channel)
            socketio.emit('user_left', {
                'username': user.username,
                'room': user.current_channel,
                'users': [{'username': u.username, 'color': u.color} for u in users.values() if u.current_channel == user.current_channel]
            }, room=user.current_channel)
    
    user.current_channel = new_ch
    join_room(new_ch)
    servers['main']['channels'][new_ch]['users'].append(user.username)
    
    socketio.emit('room_history', {
        'room': new_ch,
        'messages': servers['main']['channels'][new_ch]['messages'][-50:],
        'users': [{'username': u.username, 'color': u.color} for u in users.values() if u.current_channel == new_ch]
    }, room=request.sid)
    
    socketio.emit('user_joined', {
        'username': user.username,
        'room': new_ch,
        'users': [{'username': u.username, 'color': u.color} for u in users.values() if u.current_channel == new_ch]
    }, room=new_ch)

@socketio.on('send_message')
def handle_message(data):
    user = users.get(request.sid)
    if not user: return
    
    room = data.get('room', 'general')
    text = data.get('text', '')
    msg_type = data.get('type', 'text')
    
    msg = {
        'id': str(uuid.uuid4()),
        'username': user.username,
        'color': user.color,
        'text': text,
        'time': datetime.datetime.now().strftime('%H:%M'),
        'room': room,
        'type': msg_type,
        'role': user.roles[-1] if len(user.roles) > 1 else None,
        'filename': data.get('filename', '')
    }
    
    servers['main']['channels'][room]['messages'].append(msg)
    socketio.emit('new_message', msg, room=room)

@socketio.on('voice_join')
def handle_voice_join(data):
    user = users.get(request.sid)
    if not user: return
    
    channel = data.get('channel')
    room = f'voice_{channel}'
    join_room(room)
    
    user.voice_channel = channel
    servers['main']['voice_channels'][channel]['users'].append(user.username)
    servers['main']['voice_channels'][channel]['connections'].append(request.sid)
    
    socketio.emit('voice_user_joined', {
        'username': user.username,
        'user_id': user.id,
        'channel': channel,
        'color': user.color
    }, room=room)

@socketio.on('voice_leave')
def handle_voice_leave(data):
    user = users.get(request.sid)
    if not user: return
    
    channel = data.get('channel')
    room = f'voice_{channel}'
    leave_room(room)
    
    user.voice_channel = None
    if channel in servers['main']['voice_channels']:
        vc = servers['main']['voice_channels'][channel]
        if user.username in vc['users']: vc['users'].remove(user.username)
        if request.sid in vc['connections']: vc['connections'].remove(request.sid)
    
    socketio.emit('voice_user_left', {
        'username': user.username,
        'user_id': user.id,
        'channel': channel
    }, room=room)

@socketio.on('screen_share')
def handle_screen(data):
    room = f'voice_{data.get("channel")}'
    socketio.emit('screen_share_frame', {
        'frame': data.get('frame'),
        'username': users[request.sid].username
    }, room=room)

# WebRTC
@socketio.on('webrtc_offer')
def handle_offer(data):
    socketio.emit('webrtc_offer', {
        'from_user': request.sid,
        'offer': data['offer']
    }, room=data['to_user'])

@socketio.on('webrtc_answer')
def handle_answer(data):
    socketio.emit('webrtc_answer', {
        'from_user': request.sid,
        'answer': data['answer']
    }, room=data['to_user'])

@socketio.on('webrtc_ice')
def handle_ice(data):
    socketio.emit('webrtc_ice', {
        'from_user': request.sid,
        'candidate': data['candidate']
    }, room=data['to_user'])

if __name__ == '__main__':
    print('''
    ╔══════════════════════════════════════════╗
    ║     🎤 VoxCord - Полный Discord клон    ║
    ║                                          ║
    ║  📱 http://127.0.0.1:5000               ║
    ║  💬 Текстовый чат с эмодзи и картинками ║
    ║  🎤 Голосовой чат (WebRTC)              ║
    ║  📺 Демонстрация экрана                 ║
    ║  👥 Роли и участники                    ║
    ╚══════════════════════════════════════════╝
    ''')
    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)
