import os
import json
import time
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

# Importações condicionais para Mumble
try:
    import Ice
    import MumbleServer

    ICE_AVAILABLE = True
except ImportError:
    print("WARNING: Ice/MumbleServer não disponível. Modo simulação ativado.")
    ICE_AVAILABLE = False

# Configuração do Flask
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Criar diretórios necessários
os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('logs', exist_ok=True)
os.makedirs('backups', exist_ok=True)

# Configurações do Mumble
MUMBLE_CONFIG = {
    'host': '127.0.0.1',
    'port': 6502,
    'secret': 'AdminIgreja2024',
    'server_name': 'Igreja Avivando as Nações',
    'max_users': 100,
    'welcome_text': 'Bem-vindos à Igreja Avivando as Nações! 🙏'
}

# Configurações de autenticação
AUTH_CONFIG = {
    'admin_password': 'admin123',
    'session_timeout': 8 * 3600  # 8 horas
}

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/mumble_panel.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Banco de dados para logs e configurações
def init_database():
    conn = sqlite3.connect('mumble_panel.db')
    cursor = conn.cursor()

    # Tabela de logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            details TEXT,
            user_affected TEXT,
            channel_affected TEXT,
            admin_ip TEXT
        )
    ''')

    # Tabela de configurações
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela de usuários banidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banned_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT,
            user_hash TEXT,
            reason TEXT,
            banned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            banned_until DATETIME,
            banned_by TEXT
        )
    ''')

    # Tabela de estatísticas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            users_online INTEGER,
            channels_count INTEGER,
            bandwidth_usage REAL,
            cpu_usage REAL,
            memory_usage REAL
        )
    ''')

    # Tabela de preferências do usuário
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            preference_key TEXT UNIQUE,
            preference_value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela de cargos e permissões - CORRIGIDA
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_hash TEXT UNIQUE,
            user_name TEXT,
            role TEXT,
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            assigned_by TEXT
        )
    ''')

    # Tabela para persistir dados de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS persistent_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_hash TEXT UNIQUE,
            user_name TEXT,
            role TEXT,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            total_time INTEGER DEFAULT 0,
            notes TEXT
        )
    ''')

    conn.commit()
    conn.close()


# Classe para gerenciar persistência de dados
class UserDataManager:
    def __init__(self):
        self.db_path = 'mumble_panel.db'

    def save_user_role(self, user_hash, user_name, role, assigned_by='Admin'):
        """Salva o cargo do usuário no banco de dados"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Atualizar ou inserir na tabela user_roles
            cursor.execute('''
                INSERT OR REPLACE INTO user_roles (user_hash, user_name, role, assigned_by)
                VALUES (?, ?, ?, ?)
            ''', (user_hash, user_name, role, assigned_by))

            # Atualizar ou inserir na tabela persistent_users
            cursor.execute('''
                INSERT OR REPLACE INTO persistent_users (user_hash, user_name, role, last_seen)
                VALUES (?, ?, ?, datetime('now'))
            ''', (user_hash, user_name, role))

            conn.commit()
            conn.close()
            logger.info(f"Cargo salvo: {user_name} -> {role}")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar cargo: {e}")
            return False

    def get_user_role(self, user_hash):
        """Obtém o cargo do usuário do banco de dados"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('SELECT role FROM user_roles WHERE user_hash = ?', (user_hash,))
            result = cursor.fetchone()

            conn.close()
            return result[0] if result else 'membro'
        except Exception as e:
            logger.error(f"Erro ao obter cargo: {e}")
            return 'membro'

    def get_all_user_roles(self):
        """Obtém todos os cargos salvos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('SELECT user_hash, user_name, role FROM user_roles')
            results = cursor.fetchall()

            conn.close()
            return {row[0]: {'name': row[1], 'role': row[2]} for row in results}
        except Exception as e:
            logger.error(f"Erro ao obter todos os cargos: {e}")
            return {}

    def update_user_activity(self, user_hash, user_name, online_time=0):
        """Atualiza atividade do usuário"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO persistent_users 
                (user_hash, user_name, role, last_seen, total_time)
                VALUES (?, ?, 
                    COALESCE((SELECT role FROM persistent_users WHERE user_hash = ?), 'membro'),
                    datetime('now'), 
                    COALESCE((SELECT total_time FROM persistent_users WHERE user_hash = ?), 0) + ?)
            ''', (user_hash, user_name, user_hash, user_hash, online_time))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar atividade: {e}")
            return False


# Simulador avançado para quando Ice não está disponível
class AdvancedMumbleSimulator:
    def __init__(self, data_manager):
        self.data_manager = data_manager

        self.channels = {
            0: {
                'name': 'Root', 'parent': -1, 'description': 'Canal raiz do servidor',
                'users': [], 'temporary': False, 'position': 0, 'max_users': 0,
                'password': '', 'acl': [], 'links': []
            },
            1: {
                'name': 'Lobby Principal', 'parent': 0, 'description': 'Área de recepção da igreja',
                'users': [1, 2], 'temporary': False, 'position': 1, 'max_users': 0,
                'password': '', 'acl': [], 'links': []
            },
            2: {
                'name': 'Liderança', 'parent': 0, 'description': 'Canal exclusivo da liderança',
                'users': [3], 'temporary': False, 'position': 2, 'max_users': 10,
                'password': 'lider123', 'acl': [], 'links': []
            },
            3: {
                'name': 'Ministério de Louvor', 'parent': 0, 'description': 'Canal do ministério de louvor',
                'users': [4], 'temporary': False, 'position': 3, 'max_users': 20,
                'password': '', 'acl': [], 'links': []
            },
            4: {
                'name': 'Ministério Jovem', 'parent': 0, 'description': 'Canal do ministério jovem',
                'users': [], 'temporary': False, 'position': 4, 'max_users': 30,
                'password': '', 'acl': [], 'links': []
            },
            5: {
                'name': 'Ministério Infantil', 'parent': 0, 'description': 'Canal do ministério infantil',
                'users': [], 'temporary': False, 'position': 5, 'max_users': 15,
                'password': '', 'acl': [], 'links': []
            },
            6: {
                'name': 'Equipe Técnica', 'parent': 0, 'description': 'Canal da equipe de som e mídia',
                'users': [5], 'temporary': False, 'position': 6, 'max_users': 8,
                'password': '', 'acl': [], 'links': []
            }
        }

        # Usuários base - os cargos serão carregados do banco
        self.users = {
            1: {
                'name': 'Pastor João Silva', 'channel': 1, 'mute': False, 'deaf': False,
                'self_mute': False, 'self_deaf': False, 'suppress': False,
                'priority_speaker': True, 'recording': False, 'online_time': 3600,
                'idle_time': 0, 'bytes_per_sec': 1024, 'version': '1.4.0',
                'os': 'Windows', 'address': '192.168.1.100', 'hash': 'hash1',
                'identity': 'Pastor', 'context': '', 'comment': 'Pastor Principal',
                'role': 'pastor'
            },
            2: {
                'name': 'Maria Santos', 'channel': 1, 'mute': False, 'deaf': False,
                'self_mute': False, 'self_deaf': False, 'suppress': False,
                'priority_speaker': False, 'recording': False, 'online_time': 1800,
                'idle_time': 300, 'bytes_per_sec': 512, 'version': '1.4.0',
                'os': 'Android', 'address': '192.168.1.101', 'hash': 'hash2',
                'identity': 'Membro', 'context': '', 'comment': 'Secretária',
                'role': 'membro'
            },
            3: {
                'name': 'Pedro Oliveira', 'channel': 2, 'mute': False, 'deaf': False,
                'self_mute': False, 'self_deaf': False, 'suppress': False,
                'priority_speaker': True, 'recording': False, 'online_time': 2400,
                'idle_time': 0, 'bytes_per_sec': 768, 'version': '1.4.0',
                'os': 'Linux', 'address': '192.168.1.102', 'hash': 'hash3',
                'identity': 'Líder', 'context': '', 'comment': 'Diácono',
                'role': 'lider'
            },
            4: {
                'name': 'Ana Costa', 'channel': 3, 'mute': False, 'deaf': False,
                'self_mute': False, 'self_deaf': False, 'suppress': False,
                'priority_speaker': False, 'recording': False, 'online_time': 1200,
                'idle_time': 0, 'bytes_per_sec': 640, 'version': '1.4.0',
                'os': 'iOS', 'address': '192.168.1.103', 'hash': 'hash4',
                'identity': 'Músico', 'context': '', 'comment': 'Vocal',
                'role': 'musico'
            },
            5: {
                'name': 'Carlos Silva', 'channel': 6, 'mute': False, 'deaf': False,
                'self_mute': False, 'self_deaf': False, 'suppress': False,
                'priority_speaker': False, 'recording': False, 'online_time': 900,
                'idle_time': 0, 'bytes_per_sec': 512, 'version': '1.4.0',
                'os': 'Windows', 'address': '192.168.1.104', 'hash': 'hash5',
                'identity': 'Técnico', 'context': '', 'comment': 'Som e Mídia',
                'role': 'tecnico'
            }
        }

        # Carregar cargos salvos do banco de dados
        self.load_saved_roles()

        self.server_info = {
            'name': MUMBLE_CONFIG['server_name'],
            'users': len(self.users),
            'max_users': MUMBLE_CONFIG['max_users'],
            'channels': len(self.channels),
            'uptime': 172800,  # 2 dias em segundos
            'version': '1.4.0',
            'bandwidth': 128000,
            'welcome_text': MUMBLE_CONFIG['welcome_text'],
            'allow_html': True,
            'message_length': 5000,
            'image_message_length': 131072,
            'max_users_per_channel': 0
        }

        self.next_channel_id = 7
        self.next_user_id = 6
        self.banned_users = []
        self.server_logs = []
        self.acl_groups = {
            'admin': ['hash1'],
            'moderator': ['hash1', 'hash3'],
            'member': ['hash1', 'hash2', 'hash3', 'hash4', 'hash5']
        }

    def load_saved_roles(self):
        """Carrega cargos salvos do banco de dados"""
        try:
            saved_roles = self.data_manager.get_all_user_roles()

            for user_id, user in self.users.items():
                user_hash = user['hash']
                if user_hash in saved_roles:
                    saved_role = saved_roles[user_hash]['role']
                    user['role'] = saved_role
                    logger.info(f"Cargo carregado para {user['name']}: {saved_role}")

                    # Atualizar prioridade baseada no cargo
                    if saved_role in ['pastor', 'lider', 'diacono']:
                        user['priority_speaker'] = True
                    else:
                        user['priority_speaker'] = False

        except Exception as e:
            logger.error(f"Erro ao carregar cargos salvos: {e}")

    def update_user_role(self, user_id, new_role, assigned_by='Admin'):
        """Atualiza o cargo do usuário e salva no banco"""
        if user_id in self.users:
            user = self.users[user_id]
            old_role = user.get('role', 'membro')

            # Atualizar no simulador
            user['role'] = new_role

            # Atualizar prioridade baseada no cargo
            if new_role in ['pastor', 'lider', 'diacono']:
                user['priority_speaker'] = True
            else:
                user['priority_speaker'] = False

            # Salvar no banco de dados
            success = self.data_manager.save_user_role(
                user['hash'],
                user['name'],
                new_role,
                assigned_by
            )

            if success:
                self.log_action('CHANGE_USER_ROLE',
                                f'Cargo alterado de {old_role} para {new_role}',
                                user_affected=user['name'])
                logger.info(f"Cargo atualizado: {user['name']} -> {new_role}")
                return True
            else:
                # Reverter mudança se falhou ao salvar
                user['role'] = old_role
                return False

        return False

    def log_action(self, action, details='', user_affected='', channel_affected=''):
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'details': details,
            'user_affected': user_affected,
            'channel_affected': channel_affected
        }
        self.server_logs.append(log_entry)

        # Manter apenas os últimos 1000 logs
        if len(self.server_logs) > 1000:
            self.server_logs = self.server_logs[-1000:]

    def get_channels(self):
        return self.channels

    def get_users(self):
        # Atualizar atividade dos usuários
        for user_id, user in self.users.items():
            self.data_manager.update_user_activity(
                user['hash'],
                user['name'],
                user.get('online_time', 0)
            )
        return self.users

    def get_server_info(self):
        self.server_info['users'] = len(self.users)
        self.server_info['channels'] = len(self.channels)
        return self.server_info

    def create_channel(self, name, parent_id=0, description='', temporary=False, max_users=0, password=''):
        channel_id = self.next_channel_id
        self.next_channel_id += 1

        self.channels[channel_id] = {
            'name': name,
            'parent': parent_id,
            'description': description,
            'users': [],
            'temporary': temporary,
            'position': channel_id,
            'max_users': max_users,
            'password': password,
            'acl': [],
            'links': []
        }

        self.log_action('CREATE_CHANNEL', f'Canal "{name}" criado', channel_affected=name)
        return channel_id

    def remove_channel(self, channel_id):
        if channel_id in self.channels and channel_id != 0:
            channel_name = self.channels[channel_id]['name']

            # Mover usuários para o canal pai
            users_in_channel = self.channels[channel_id]['users'][:]
            parent_id = self.channels[channel_id]['parent']

            for user_id in users_in_channel:
                if user_id in self.users:
                    self.users[user_id]['channel'] = parent_id
                    if parent_id in self.channels:
                        self.channels[parent_id]['users'].append(user_id)

            del self.channels[channel_id]
            self.log_action('REMOVE_CHANNEL', f'Canal "{channel_name}" removido', channel_affected=channel_name)
            return True
        return False

    def move_user(self, user_id, channel_id):
        if user_id in self.users and channel_id in self.channels:
            old_channel = self.users[user_id]['channel']
            user_name = self.users[user_id]['name']

            # Remover do canal antigo
            if old_channel in self.channels and user_id in self.channels[old_channel]['users']:
                self.channels[old_channel]['users'].remove(user_id)

            # Adicionar ao novo canal
            self.users[user_id]['channel'] = channel_id
            if user_id not in self.channels[channel_id]['users']:
                self.channels[channel_id]['users'].append(user_id)

            old_channel_name = self.channels.get(old_channel, {}).get('name', 'Desconhecido')
            new_channel_name = self.channels[channel_id]['name']

            self.log_action('MOVE_USER', f'Usuário movido de "{old_channel_name}" para "{new_channel_name}"',
                            user_affected=user_name, channel_affected=new_channel_name)
            return True
        return False

    def kick_user(self, user_id, reason=''):
        if user_id in self.users:
            user_name = self.users[user_id]['name']
            channel_id = self.users[user_id]['channel']

            # Remover do canal
            if channel_id in self.channels and user_id in self.channels[channel_id]['users']:
                self.channels[channel_id]['users'].remove(user_id)

            del self.users[user_id]
            self.log_action('KICK_USER', f'Usuário expulso. Motivo: {reason}', user_affected=user_name)
            return True
        return False

    def ban_user(self, user_id, reason='', duration_hours=0):
        if user_id in self.users:
            user = self.users[user_id]
            user_name = user['name']
            user_hash = user['hash']

            ban_entry = {
                'user_name': user_name,
                'user_hash': user_hash,
                'reason': reason,
                'banned_at': datetime.now(),
                'banned_until': datetime.now() + timedelta(hours=duration_hours) if duration_hours > 0 else None,
                'banned_by': 'Admin'
            }

            self.banned_users.append(ban_entry)
            self.kick_user(user_id, f'Banido: {reason}')
            self.log_action('BAN_USER', f'Usuário banido. Motivo: {reason}. Duração: {duration_hours}h',
                            user_affected=user_name)
            return True
        return False

    def unban_user(self, user_hash):
        for i, ban in enumerate(self.banned_users):
            if ban['user_hash'] == user_hash:
                user_name = ban['user_name']
                del self.banned_users[i]
                self.log_action('UNBAN_USER', 'Usuário desbanido', user_affected=user_name)
                return True
        return False

    def send_message(self, message, channel_id=None, user_id=None):
        if channel_id and channel_id in self.channels:
            channel_name = self.channels[channel_id]['name']
            self.log_action('SEND_MESSAGE_CHANNEL', f'Mensagem enviada para canal "{channel_name}": {message[:50]}...',
                            channel_affected=channel_name)
            return True
        elif user_id and user_id in self.users:
            user_name = self.users[user_id]['name']
            self.log_action('SEND_MESSAGE_USER', f'Mensagem privada enviada para "{user_name}": {message[:50]}...',
                            user_affected=user_name)
            return True
        return False

    def mute_user(self, user_id, mute=True):
        if user_id in self.users:
            user_name = self.users[user_id]['name']
            self.users[user_id]['mute'] = mute
            action = 'MUTE_USER' if mute else 'UNMUTE_USER'
            self.log_action(action, f'Usuário {"silenciado" if mute else "dessilenciado"}', user_affected=user_name)
            return True
        return False

    def deafen_user(self, user_id, deaf=True):
        if user_id in self.users:
            user_name = self.users[user_id]['name']
            self.users[user_id]['deaf'] = deaf
            action = 'DEAFEN_USER' if deaf else 'UNDEAFEN_USER'
            self.log_action(action, f'Usuário {"ensurdecido" if deaf else "desensurdecido"}', user_affected=user_name)
            return True
        return False

    def set_priority_speaker(self, user_id, priority=True):
        if user_id in self.users:
            user_name = self.users[user_id]['name']
            self.users[user_id]['priority_speaker'] = priority
            self.log_action('SET_PRIORITY_SPEAKER', f'Prioridade de fala {"ativada" if priority else "desativada"}',
                            user_affected=user_name)
            return True
        return False

    def get_logs(self, limit=100):
        return self.server_logs[-limit:]

    def get_banned_users(self):
        return self.banned_users


# Classe principal do controlador Mumble
class AdvancedMumbleController:
    def __init__(self):
        self.data_manager = UserDataManager()
        self.server = None
        self.connected = False
        self.simulation_mode = not ICE_AVAILABLE
        self.ctx = {"secret": MUMBLE_CONFIG['secret']}
        self.monitoring_active = False
        self.monitoring_thread = None

        if self.simulation_mode:
            self.server = AdvancedMumbleSimulator(self.data_manager)
            self.connected = True
            logger.info("Modo simulação ativado")
        else:
            self.connect()

        # Iniciar monitoramento
        self.start_monitoring()

    def connect(self):
        """Conecta ao servidor Mumble real"""
        try:
            # Configurar ICE
            init_data = Ice.InitializationData()
            init_data.properties = Ice.createProperties()
            init_data.properties.setProperty("Ice.ImplicitContext", "Shared")
            init_data.properties.setProperty("Ice.Default.EncodingVersion", "1.0")

            self.communicator = Ice.initialize([], init_data)

            # Configurar autenticação
            ic = self.communicator.getImplicitContext()
            if ic:
                ic.put("secret", MUMBLE_CONFIG['secret'])

            # Conectar ao servidor
            proxy_string = f"Meta:tcp -h {MUMBLE_CONFIG['host']} -p {MUMBLE_CONFIG['port']} -t 60000"
            base = self.communicator.stringToProxy(proxy_string)
            meta = MumbleServer.MetaPrx.checkedCast(base, self.ctx)

            if not meta:
                raise Exception("Falha ao conectar ao Meta servidor")

            # Obter primeiro servidor
            servers = meta.getAllServers(self.ctx)
            if not servers:
                raise Exception("Nenhum servidor encontrado")

            self.server = servers[0]

            # Iniciar servidor se necessário
            if not self.server.isRunning(self.ctx):
                self.server.start(self.ctx)

            self.connected = True
            logger.info(f"Conectado ao servidor Mumble ID {self.server.id(self.ctx)}")
            return True

        except Exception as e:
            logger.error(f"Erro na conexão: {e}")
            logger.info("Ativando modo simulação")
            self.server = AdvancedMumbleSimulator(self.data_manager)
            self.simulation_mode = True
            self.connected = True
            return False

    def start_monitoring(self):
        """Inicia monitoramento em background"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()
            logger.info("Monitoramento iniciado")

    def _monitoring_loop(self):
        """Loop de monitoramento"""
        while self.monitoring_active:
            try:
                # Coletar estatísticas
                if self.connected:
                    stats = self.get_server_stats()
                    self._save_stats(stats)

                time.sleep(60)  # Coletar a cada minuto
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}")
                time.sleep(60)

    def _save_stats(self, stats):
        """Salva estatísticas no banco"""
        try:
            conn = sqlite3.connect('mumble_panel.db')
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO server_stats (users_online, channels_count, bandwidth_usage, cpu_usage, memory_usage)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                stats.get('users', 0),
                stats.get('channels', 0),
                stats.get('bandwidth', 0),
                0,  # CPU usage
                0  # Memory usage
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Erro ao salvar estatísticas: {e}")

    def log_activity(self, action, details='', user_affected='', channel_affected='', admin_ip=''):
        """Registra atividade no banco"""
        try:
            conn = sqlite3.connect('mumble_panel.db')
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO activity_logs (action, details, user_affected, channel_affected, admin_ip)
                VALUES (?, ?, ?, ?, ?)
            ''', (action, details, user_affected, channel_affected, admin_ip))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Erro ao registrar log: {e}")

    def get_server_status(self):
        """Obtém status detalhado do servidor"""
        if self.simulation_mode:
            info = self.server.get_server_info()
            info['mode'] = 'Simulação'
            info['connection_status'] = 'Conectado (Simulação)'
            return info

        try:
            users = self.server.getUsers(self.ctx)
            channels = self.server.getChannels(self.ctx)

            return {
                'name': MUMBLE_CONFIG['server_name'],
                'users': len(users),
                'max_users': MUMBLE_CONFIG['max_users'],
                'channels': len(channels),
                'uptime': 'Conectado',
                'mode': 'Real',
                'connection_status': 'Conectado',
                'version': '1.4.0',
                'bandwidth': 128000
            }
        except Exception as e:
            return {'error': str(e), 'connection_status': 'Erro'}

    def get_server_stats(self):
        """Obtém estatísticas do servidor"""
        if self.simulation_mode:
            return self.server.get_server_info()

        try:
            users = self.server.getUsers(self.ctx)
            channels = self.server.getChannels(self.ctx)

            return {
                'users': len(users),
                'channels': len(channels),
                'bandwidth': 128000
            }
        except Exception as e:
            return {'users': 0, 'channels': 0, 'bandwidth': 0}

    # Métodos de gerenciamento
    def get_channels(self):
        if self.simulation_mode:
            return self.server.get_channels()

        try:
            channels = self.server.getChannels(self.ctx)
            result = {}
            for channel_id, channel_state in channels.items():
                result[channel_id] = {
                    'name': channel_state.name,
                    'parent': channel_state.parent,
                    'description': getattr(channel_state, 'description', ''),
                    'users': [],
                    'temporary': getattr(channel_state, 'temporary', False),
                    'position': getattr(channel_state, 'position', 0),
                    'max_users': getattr(channel_state, 'maxUsers', 0),
                    'password': '',
                    'acl': [],
                    'links': []
                }
            return result
        except Exception as e:
            logger.error(f"Erro ao obter canais: {e}")
            return {}

    def get_users(self):
        if self.simulation_mode:
            return self.server.get_users()

        try:
            users = self.server.getUsers(self.ctx)
            result = {}
            for user_id, user_state in users.items():
                user_hash = getattr(user_state, 'hash', f'hash_{user_id}')
                saved_role = self.data_manager.get_user_role(user_hash)

                result[user_id] = {
                    'name': user_state.name,
                    'channel': user_state.channel,
                    'mute': getattr(user_state, 'mute', False),
                    'deaf': getattr(user_state, 'deaf', False),
                    'self_mute': getattr(user_state, 'selfMute', False),
                    'self_deaf': getattr(user_state, 'selfDeaf', False),
                    'suppress': getattr(user_state, 'suppress', False),
                    'priority_speaker': getattr(user_state, 'prioritySpeaker', False),
                    'recording': getattr(user_state, 'recording', False),
                    'online_time': getattr(user_state, 'onlinesecs', 0),
                    'idle_time': getattr(user_state, 'idlesecs', 0),
                    'bytes_per_sec': getattr(user_state, 'bytespersec', 0),
                    'version': getattr(user_state, 'version', ''),
                    'os': getattr(user_state, 'os', ''),
                    'address': getattr(user_state, 'address', ''),
                    'hash': user_hash,
                    'identity': getattr(user_state, 'identity', ''),
                    'context': getattr(user_state, 'context', ''),
                    'comment': getattr(user_state, 'comment', ''),
                    'role': saved_role  # Carregar do banco
                }
            return result
        except Exception as e:
            logger.error(f"Erro ao obter usuários: {e}")
            return {}

    # Método específico para mudança de cargo
    def change_user_role(self, user_id, new_role, assigned_by='Admin'):
        """Muda o cargo do usuário de forma persistente"""
        if self.simulation_mode:
            return self.server.update_user_role(user_id, new_role, assigned_by)

        # Para servidor real, salvar no banco e aplicar lógica
        try:
            users = self.get_users()
            if user_id in users:
                user = users[user_id]
                user_hash = user['hash']
                user_name = user['name']

                # Salvar no banco
                success = self.data_manager.save_user_role(user_hash, user_name, new_role, assigned_by)

                if success:
                    # Aplicar prioridade se necessário
                    if new_role in ['pastor', 'lider', 'diacono']:
                        self.set_priority_speaker(user_id, True)

                    self.log_activity('CHANGE_USER_ROLE',
                                      f'Cargo alterado para {new_role}',
                                      user_affected=user_name,
                                      admin_ip=request.remote_addr if request else '')
                    return True

            return False
        except Exception as e:
            logger.error(f"Erro ao alterar cargo: {e}")
            return False

    # Métodos de controle (mantidos iguais)
    def create_channel(self, name, parent_id=0, description='', temporary=False, max_users=0, password=''):
        if self.simulation_mode:
            return self.server.create_channel(name, parent_id, description, temporary, max_users, password)

        try:
            channel_id = self.server.addChannel(name, parent_id, self.ctx)
            self.log_activity('CREATE_CHANNEL', f'Canal "{name}" criado', channel_affected=name,
                              admin_ip=request.remote_addr if request else '')
            return channel_id
        except Exception as e:
            logger.error(f"Erro ao criar canal: {e}")
            return None

    def remove_channel(self, channel_id):
        if self.simulation_mode:
            return self.server.remove_channel(channel_id)

        try:
            self.server.removeChannel(channel_id, self.ctx)
            self.log_activity('REMOVE_CHANNEL', f'Canal ID {channel_id} removido',
                              admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao remover canal: {e}")
            return False

    def move_user(self, user_id, channel_id):
        if self.simulation_mode:
            return self.server.move_user(user_id, channel_id)

        try:
            user_state = self.server.getState(user_id, self.ctx)
            user_state.channel = channel_id
            self.server.setState(user_state, self.ctx)

            users = self.get_users()
            user_name = users.get(user_id, {}).get('name', 'Desconhecido')
            channels = self.get_channels()
            channel_name = channels.get(channel_id, {}).get('name', 'Desconhecido')

            self.log_activity('MOVE_USER', f'Usuário movido para canal "{channel_name}"',
                              user_affected=user_name, channel_affected=channel_name,
                              admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao mover usuário: {e}")
            return False

    def kick_user(self, user_id, reason=''):
        if self.simulation_mode:
            return self.server.kick_user(user_id, reason)

        try:
            users = self.get_users()
            user_name = users.get(user_id, {}).get('name', 'Desconhecido')

            self.server.kickUser(user_id, reason, self.ctx)
            self.log_activity('KICK_USER', f'Usuário expulso. Motivo: {reason}',
                              user_affected=user_name, admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao expulsar usuário: {e}")
            return False

    def ban_user(self, user_id, reason='', duration_hours=0):
        if self.simulation_mode:
            return self.server.ban_user(user_id, reason, duration_hours)

        try:
            users = self.get_users()
            user = users.get(user_id, {})
            user_name = user.get('name', 'Desconhecido')
            user_hash = user.get('hash', '')

            self.server.banUser(user_id, reason, self.ctx)

            # Registrar no banco local
            conn = sqlite3.connect('mumble_panel.db')
            cursor = conn.cursor()

            banned_until = None
            if duration_hours > 0:
                banned_until = datetime.now() + timedelta(hours=duration_hours)

            cursor.execute('''
                INSERT INTO banned_users (user_name, user_hash, reason, banned_until, banned_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_name, user_hash, reason, banned_until, 'Admin'))

            conn.commit()
            conn.close()

            self.log_activity('BAN_USER', f'Usuário banido. Motivo: {reason}. Duração: {duration_hours}h',
                              user_affected=user_name, admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao banir usuário: {e}")
            return False

    def send_message(self, message, channel_id=None, user_id=None):
        if self.simulation_mode:
            return self.server.send_message(message, channel_id, user_id)

        try:
            if channel_id:
                self.server.sendMessageChannel(channel_id, False, message, self.ctx)
                channels = self.get_channels()
                channel_name = channels.get(channel_id, {}).get('name', 'Desconhecido')
                self.log_activity('SEND_MESSAGE_CHANNEL', f'Mensagem enviada para canal "{channel_name}"',
                                  channel_affected=channel_name, admin_ip=request.remote_addr if request else '')
            elif user_id:
                self.server.sendMessage(user_id, message, self.ctx)
                users = self.get_users()
                user_name = users.get(user_id, {}).get('name', 'Desconhecido')
                self.log_activity('SEND_MESSAGE_USER', f'Mensagem privada enviada',
                                  user_affected=user_name, admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return False

    def mute_user(self, user_id, mute=True):
        if self.simulation_mode:
            return self.server.mute_user(user_id, mute)

        try:
            user_state = self.server.getState(user_id, self.ctx)
            user_state.mute = mute
            self.server.setState(user_state, self.ctx)

            users = self.get_users()
            user_name = users.get(user_id, {}).get('name', 'Desconhecido')
            action = 'MUTE_USER' if mute else 'UNMUTE_USER'
            self.log_activity(action, f'Usuário {"silenciado" if mute else "dessilenciado"}',
                              user_affected=user_name, admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao silenciar usuário: {e}")
            return False

    def deafen_user(self, user_id, deaf=True):
        if self.simulation_mode:
            return self.server.deafen_user(user_id, deaf)

        try:
            user_state = self.server.getState(user_id, self.ctx)
            user_state.deaf = deaf
            self.server.setState(user_state, self.ctx)

            users = self.get_users()
            user_name = users.get(user_id, {}).get('name', 'Desconhecido')
            action = 'DEAFEN_USER' if deaf else 'UNDEAFEN_USER'
            self.log_activity(action, f'Usuário {"ensurdecido" if deaf else "desensurdecido"}',
                              user_affected=user_name, admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao ensurdecer usuário: {e}")
            return False

    def set_priority_speaker(self, user_id, priority=True):
        if self.simulation_mode:
            return self.server.set_priority_speaker(user_id, priority)

        try:
            user_state = self.server.getState(user_id, self.ctx)
            user_state.prioritySpeaker = priority
            self.server.setState(user_state, self.ctx)

            users = self.get_users()
            user_name = users.get(user_id, {}).get('name', 'Desconhecido')
            self.log_activity('SET_PRIORITY_SPEAKER', f'Prioridade de fala {"ativada" if priority else "desativada"}',
                              user_affected=user_name, admin_ip=request.remote_addr if request else '')
            return True
        except Exception as e:
            logger.error(f"Erro ao definir prioridade: {e}")
            return False

    def get_activity_logs(self, limit=100):
        """Obtém logs de atividade"""
        if self.simulation_mode:
            return self.server.get_logs(limit)

        try:
            conn = sqlite3.connect('mumble_panel.db')
            cursor = conn.cursor()

            cursor.execute('''
                SELECT timestamp, action, details, user_affected, channel_affected, admin_ip
                FROM activity_logs
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'timestamp': row[0],
                    'action': row[1],
                    'details': row[2],
                    'user_affected': row[3],
                    'channel_affected': row[4],
                    'admin_ip': row[5]
                })

            conn.close()
            return logs
        except Exception as e:
            logger.error(f"Erro ao obter logs: {e}")
            return []

    def get_banned_users(self):
        """Obtém lista de usuários banidos"""
        if self.simulation_mode:
            return self.server.get_banned_users()

        try:
            conn = sqlite3.connect('mumble_panel.db')
            cursor = conn.cursor()

            cursor.execute('''
                SELECT user_name, user_hash, reason, banned_at, banned_until, banned_by
                FROM banned_users
                ORDER BY banned_at DESC
            ''')

            banned = []
            for row in cursor.fetchall():
                banned.append({
                    'user_name': row[0],
                    'user_hash': row[1],
                    'reason': row[2],
                    'banned_at': row[3],
                    'banned_until': row[4],
                    'banned_by': row[5]
                })

            conn.close()
            return banned
        except Exception as e:
            logger.error(f"Erro ao obter usuários banidos: {e}")
            return []


# Instância global do controlador
mumble = AdvancedMumbleController()

# Inicializar banco de dados
init_database()


# Funções de preferências do usuário
def get_user_preference(key, default=None):
    try:
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()
        cursor.execute('SELECT preference_value FROM user_preferences WHERE preference_key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default
    except:
        return default


def set_user_preference(key, value):
    try:
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_preferences (preference_key, preference_value)
            VALUES (?, ?)
        ''', (key, value))
        conn.commit()
        conn.close()
        return True
    except:
        return False


# Middleware de autenticação
def check_auth():
    return request.cookies.get('authenticated') == 'true'


def require_auth(f):
    def decorated(*args, **kwargs):
        if not check_auth():
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    decorated.__name__ = f.__name__
    return decorated


# Rotas principais
@app.route('/')
def index():
    if not check_auth():
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    server_status = mumble.get_server_status()
    dark_mode = get_user_preference('dark_mode', 'false') == 'true'

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == AUTH_CONFIG['admin_password']:
            response = redirect(url_for('dashboard'))
            response.set_cookie('authenticated', 'true', max_age=AUTH_CONFIG['session_timeout'])

            mumble.log_activity('ADMIN_LOGIN', 'Administrador fez login', admin_ip=request.remote_addr)
            flash('Login realizado com sucesso!', 'success')
            return response
        else:
            flash('Usuário ou senha incorretos!', 'error')
            mumble.log_activity('ADMIN_LOGIN_FAILED', 'Tentativa de login falhada', admin_ip=request.remote_addr)

    return render_template('login.html', server_status=server_status, dark_mode=dark_mode)


@app.route('/logout')
def logout():
    mumble.log_activity('ADMIN_LOGOUT', 'Administrador fez logout', admin_ip=request.remote_addr)
    response = redirect(url_for('login'))
    response.set_cookie('authenticated', '', expires=0)
    return response


@app.route('/dashboard')
@require_auth
def dashboard():
    server_status = mumble.get_server_status()
    channels = mumble.get_channels()
    users = mumble.get_users()
    recent_logs = mumble.get_activity_logs(10)

    # Estatísticas adicionais
    stats = {
        'total_channels': len(channels),
        'total_users': len(users),
        'users_speaking': len(
            [u for u in users.values() if not u.get('mute', False) and not u.get('self_mute', False)]),
        'priority_speakers': len([u for u in users.values() if u.get('priority_speaker', False)]),
        'muted_users': len([u for u in users.values() if u.get('mute', False)]),
        'deafened_users': len([u for u in users.values() if u.get('deaf', False)])
    }

    dark_mode = get_user_preference('dark_mode', 'false') == 'true'

    return render_template('dashboard.html',
                           server_status=server_status,
                           channels=channels,
                           users=users,
                           recent_logs=recent_logs,
                           stats=stats,
                           dark_mode=dark_mode)


@app.route('/channels')
@require_auth
def channels():
    channels = mumble.get_channels()
    users = mumble.get_users()
    server_status = mumble.get_server_status()

    # Organizar usuários por canal
    for channel_id, channel in channels.items():
        channel['user_list'] = [users[uid] for uid in users if users[uid]['channel'] == channel_id]

    dark_mode = get_user_preference('dark_mode', 'false') == 'true'
    return render_template('channels.html', channels=channels, users=users, server_status=server_status,
                           dark_mode=dark_mode)


@app.route('/users')
@require_auth
def users():
    users = mumble.get_users()
    channels = mumble.get_channels()
    banned_users = mumble.get_banned_users()
    server_status = mumble.get_server_status()

    dark_mode = get_user_preference('dark_mode', 'false') == 'true'
    return render_template('users.html', users=users, channels=channels, banned_users=banned_users,
                           server_status=server_status, dark_mode=dark_mode)


@app.route('/logs')
@require_auth
def logs():
    logs = mumble.get_activity_logs(200)
    server_status = mumble.get_server_status()
    dark_mode = get_user_preference('dark_mode', 'false') == 'true'
    return render_template('logs.html', logs=logs, server_status=server_status, dark_mode=dark_mode)


@app.route('/settings')
@require_auth
def settings():
    server_status = mumble.get_server_status()
    dark_mode = get_user_preference('dark_mode', 'false') == 'true'
    return render_template('settings.html', server_status=server_status, mumble_config=MUMBLE_CONFIG,
                           dark_mode=dark_mode)


# APIs - Todas as funcionalidades necessárias
@app.route('/api/create_channel', methods=['POST'])
@require_auth
def api_create_channel():
    data = request.get_json()
    name = data.get('name')
    parent_id = data.get('parent_id', 0)
    description = data.get('description', '')
    temporary = data.get('temporary', False)
    max_users = data.get('max_users', 0)
    password = data.get('password', '')

    if not name:
        return jsonify({'success': False, 'error': 'Nome é obrigatório'})

    channel_id = mumble.create_channel(name, parent_id, description, temporary, max_users, password)
    if channel_id:
        return jsonify({'success': True, 'channel_id': channel_id})
    else:
        return jsonify({'success': False, 'error': 'Erro ao criar canal'})


@app.route('/api/remove_channel', methods=['POST'])
@require_auth
def api_remove_channel():
    data = request.get_json()
    channel_id = data.get('channel_id')

    if mumble.remove_channel(channel_id):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao remover canal'})


@app.route('/api/move_user', methods=['POST'])
@require_auth
def api_move_user():
    data = request.get_json()
    user_id = data.get('user_id')
    channel_id = data.get('channel_id')

    if mumble.move_user(user_id, channel_id):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao mover usuário'})


@app.route('/api/kick_user', methods=['POST'])
@require_auth
def api_kick_user():
    data = request.get_json()
    user_id = data.get('user_id')
    reason = data.get('reason', '')

    if mumble.kick_user(user_id, reason):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao expulsar usuário'})


@app.route('/api/ban_user', methods=['POST'])
@require_auth
def api_ban_user():
    data = request.get_json()
    user_id = data.get('user_id')
    reason = data.get('reason', '')
    duration_hours = data.get('duration_hours', 0)

    if mumble.ban_user(user_id, reason, duration_hours):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao banir usuário'})


@app.route('/api/unban_user', methods=['POST'])
@require_auth
def api_unban_user():
    data = request.get_json()
    user_hash = data.get('user_hash')

    if not user_hash:
        return jsonify({'success': False, 'error': 'Hash do usuário é obrigatório'})

    try:
        # Remover do banco de dados local
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()

        cursor.execute('DELETE FROM banned_users WHERE user_hash = ?', (user_hash,))
        affected_rows = cursor.rowcount

        conn.commit()
        conn.close()

        if affected_rows > 0:
            mumble.log_activity('UNBAN_USER', 'Usuário desbanido', admin_ip=request.remote_addr)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Usuário não encontrado na lista de banidos'})

    except Exception as e:
        logger.error(f"Erro ao desbanir usuário: {e}")
        return jsonify({'success': False, 'error': 'Erro interno do servidor'})


@app.route('/api/send_message', methods=['POST'])
@require_auth
def api_send_message():
    data = request.get_json()
    message = data.get('message')
    channel_id = data.get('channel_id')
    user_id = data.get('user_id')

    if mumble.send_message(message, channel_id, user_id):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao enviar mensagem'})


@app.route('/api/mute_user', methods=['POST'])
@require_auth
def api_mute_user():
    data = request.get_json()
    user_id = data.get('user_id')
    mute = data.get('mute', True)

    if mumble.mute_user(user_id, mute):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao silenciar usuário'})


@app.route('/api/deafen_user', methods=['POST'])
@require_auth
def api_deafen_user():
    data = request.get_json()
    user_id = data.get('user_id')
    deaf = data.get('deaf', True)

    if mumble.deafen_user(user_id, deaf):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao ensurdecer usuário'})


@app.route('/api/set_priority_speaker', methods=['POST'])
@require_auth
def api_set_priority_speaker():
    data = request.get_json()
    user_id = data.get('user_id')
    priority = data.get('priority', True)

    if mumble.set_priority_speaker(user_id, priority):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao definir prioridade'})


@app.route('/api/refresh_data')
@require_auth
def api_refresh_data():
    return jsonify({
        'server_status': mumble.get_server_status(),
        'channels': mumble.get_channels(),
        'users': mumble.get_users(),
        'recent_logs': mumble.get_activity_logs(5)
    })


@app.route('/api/get_stats')
@require_auth
def api_get_stats():
    """API para gráficos e estatísticas"""
    try:
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()

        # Estatísticas das últimas 24 horas
        cursor.execute('''
            SELECT timestamp, users_online, channels_count, bandwidth_usage
            FROM server_stats
            WHERE timestamp > datetime('now', '-24 hours')
            ORDER BY timestamp
        ''')

        stats = []
        for row in cursor.fetchall():
            stats.append({
                'timestamp': row[0],
                'users': row[1],
                'channels': row[2],
                'bandwidth': row[3]
            })

        conn.close()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/update_server_config', methods=['POST'])
@require_auth
def api_update_server_config():
    data = request.get_json()

    # Atualizar configurações no banco
    try:
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()

        for key, value in data.items():
            cursor.execute('''
                INSERT OR REPLACE INTO server_config (key, value)
                VALUES (?, ?)
            ''', (key, str(value)))

        conn.commit()
        conn.close()

        mumble.log_activity('UPDATE_CONFIG', f'Configurações atualizadas: {list(data.keys())}',
                            admin_ip=request.remote_addr)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/toggle_dark_mode', methods=['POST'])
@require_auth
def api_toggle_dark_mode():
    data = request.get_json()
    dark_mode = data.get('dark_mode', False)

    if set_user_preference('dark_mode', 'true' if dark_mode else 'false'):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Erro ao salvar preferência'})


@app.route('/api/change_user_role', methods=['POST'])
@require_auth
def api_change_user_role():
    data = request.get_json()
    user_id = data.get('user_id')
    new_role = data.get('new_role')
    reason = data.get('reason', '')
    notify_user = data.get('notify_user', False)

    if user_id and new_role:
        # Usar o método específico para mudança de cargo
        success = mumble.change_user_role(user_id, new_role, 'Admin')

        if success:
            # Enviar notificação se solicitado
            if notify_user:
                users = mumble.get_users()
                if user_id in users:
                    user_name = users[user_id]['name']
                    message = f"Seu cargo foi alterado para {new_role.title()}. Motivo: {reason}"
                    mumble.send_message(message, user_id=user_id)

            return jsonify({'success': True, 'message': f'Cargo alterado para {new_role} com sucesso!'})
        else:
            return jsonify({'success': False, 'error': 'Erro ao alterar cargo do usuário'})
    else:
        return jsonify({'success': False, 'error': 'Dados inválidos - user_id e new_role são obrigatórios'})


@app.route('/api/bulk_user_action', methods=['POST'])
@require_auth
def api_bulk_user_action():
    data = request.get_json()
    action = data.get('action')
    user_ids = data.get('user_ids', [])
    reason = data.get('reason', '')
    channel_id = data.get('channel_id')
    role = data.get('role')
    ban_duration = data.get('ban_duration', 0)

    if not user_ids:
        return jsonify({'success': False, 'error': 'Nenhum usuário selecionado'})

    success_count = 0
    failed_count = 0

    for user_id in user_ids:
        try:
            if action == 'mute':
                if mumble.mute_user(user_id, True):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'unmute':
                if mumble.mute_user(user_id, False):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'mute_except_priority':
                users = mumble.get_users()
                if user_id in users and not users[user_id].get('priority_speaker', False):
                    if mumble.mute_user(user_id, True):
                        success_count += 1
                    else:
                        failed_count += 1
                else:
                    # Usuário é prioritário, não silenciar
                    continue
            elif action == 'deafen':
                if mumble.deafen_user(user_id, True):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'undeafen':
                if mumble.deafen_user(user_id, False):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'priority':
                if mumble.set_priority_speaker(user_id, True):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'unpriority':
                if mumble.set_priority_speaker(user_id, False):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'move' and channel_id:
                if mumble.move_user(user_id, channel_id):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'kick':
                if mumble.kick_user(user_id, reason):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'ban':
                if mumble.ban_user(user_id, reason, ban_duration):
                    success_count += 1
                else:
                    failed_count += 1
            elif action == 'role' and role:
                # Usar o método específico para mudança de cargo
                if mumble.change_user_role(user_id, role, 'Admin'):
                    success_count += 1
                else:
                    failed_count += 1
            else:
                failed_count += 1

        except Exception as e:
            logger.error(f"Erro na ação em massa para usuário {user_id}: {e}")
            failed_count += 1

    mumble.log_activity('BULK_USER_ACTION',
                        f'Ação "{action}" executada em {success_count}/{len(user_ids)} usuários. Motivo: {reason}',
                        admin_ip=request.remote_addr)

    if success_count > 0:
        message = f'Ação executada com sucesso em {success_count} usuário(s)'
        if failed_count > 0:
            message += f'. {failed_count} falharam.'
        return jsonify({'success': True, 'affected_users': success_count, 'message': message})
    else:
        return jsonify({'success': False, 'error': f'Nenhuma ação foi executada com sucesso. {failed_count} falharam.'})


@app.route('/api/organize_users_by_role', methods=['POST'])
@require_auth
def api_organize_users_by_role():
    """Organiza usuários por cargo nos canais apropriados"""
    try:
        users = mumble.get_users()
        channels = mumble.get_channels()

        # Mapeamento de cargos para canais
        role_channel_map = {
            'pastor': 2,  # Liderança
            'lider': 2,  # Liderança
            'diacono': 2,  # Liderança
            'musico': 3,  # Ministério de Louvor
            'tecnico': 6,  # Equipe Técnica
            'membro': 1,  # Lobby Principal
            'visitante': 1  # Lobby Principal
        }

        moved_count = 0
        for user_id, user in users.items():
            user_role = user.get('role', 'membro')
            target_channel = role_channel_map.get(user_role, 1)

            if user['channel'] != target_channel:
                if mumble.move_user(user_id, target_channel):
                    moved_count += 1

        mumble.log_activity('ORGANIZE_BY_ROLE', f'{moved_count} usuários organizados por cargo',
                            admin_ip=request.remote_addr)

        return jsonify(
            {'success': True, 'moved_users': moved_count, 'message': f'{moved_count} usuários organizados por cargo'})
    except Exception as e:
        logger.error(f"Erro ao organizar usuários por cargo: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/save_role_configuration', methods=['POST'])
@require_auth
def api_save_role_configuration():
    """Salva configurações de cargos"""
    data = request.get_json()

    try:
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()

        for key, value in data.items():
            cursor.execute('''
                INSERT OR REPLACE INTO server_config (key, value)
                VALUES (?, ?)
            ''', (f'role_config_{key}', str(value)))

        conn.commit()
        conn.close()

        mumble.log_activity('SAVE_ROLE_CONFIG', 'Configurações de cargos salvas',
                            admin_ip=request.remote_addr)

        return jsonify({'success': True, 'message': 'Configurações de cargos salvas com sucesso!'})
    except Exception as e:
        logger.error(f"Erro ao salvar configurações de cargos: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/clear_expired_bans', methods=['POST'])
@require_auth
def api_clear_expired_bans():
    """Remove banimentos expirados"""
    try:
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM banned_users 
            WHERE banned_until IS NOT NULL AND banned_until < datetime('now')
        ''')

        cleared_count = cursor.rowcount
        conn.commit()
        conn.close()

        mumble.log_activity('CLEAR_EXPIRED_BANS', f'{cleared_count} banimentos expirados removidos',
                            admin_ip=request.remote_addr)

        return jsonify({'success': True, 'cleared_count': cleared_count,
                        'message': f'{cleared_count} banimentos expirados removidos'})
    except Exception as e:
        logger.error(f"Erro ao limpar banimentos expirados: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/save_settings', methods=['POST'])
@require_auth
def save_settings():
    """Salva configurações do cliente"""
    data = request.get_json()

    try:
        conn = sqlite3.connect('mumble_panel.db')
        cursor = conn.cursor()

        # Salvar configurações como JSON
        settings_json = json.dumps(data)
        cursor.execute('''
            INSERT OR REPLACE INTO server_config (key, value)
            VALUES (?, ?)
        ''', ('client_settings', settings_json))

        conn.commit()
        conn.close()

        mumble.log_activity('SAVE_CLIENT_SETTINGS', 'Configurações do cliente salvas',
                            admin_ip=request.remote_addr)

        return jsonify({'success': True, 'message': 'Configurações salvas com sucesso!'})
    except Exception as e:
        logger.error(f"Erro ao salvar configurações: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve arquivos estáticos"""
    return send_file(os.path.join('static', filename))




if __name__ == '__main__':
    print("PAINEL MUMBLE AVANÇADO - IGREJA AVIVANDO AS NAÇÕES")
    print("=" * 70)
    print(f"Acesse: http://127.0.0.1:5000")
    print(f"Usuário: admin")
    print(f"Senha: {AUTH_CONFIG['admin_password']}")
    print(f"Modo: {'Simulação' if mumble.simulation_mode else 'Real'}")
    print(f"Monitoramento: {'Ativo' if mumble.monitoring_active else 'Inativo'}")
    print("=" * 70)
    print("Funcionalidades disponíveis:")
    print("   • Dashboard com estatísticas em tempo real")
    print("   • Gerenciamento completo de canais")
    print("   • Controle total de usuários com cargos PERSISTENTES")
    print("   • Sistema de mensagens globais e privadas")
    print("   • Logs de atividade detalhados")
    print("   • Configurações avançadas do servidor")
    print("   • Sistema de banimento com duração")
    print("   • Oradores prioritários por cargo")
    print("   • Ações em massa para usuários")
    print("   • Interface moderna e responsiva")
    print("   • Modo escuro/claro")
    print("   • Organização automática por cargos")
    print("   • Filtros avançados de usuários")
    print("   • Exportação de dados")
    print("   • PERSISTÊNCIA DE CARGOS NO BANCO DE DADOS")
    print("=" * 70)

    try:
        app.run(debug=True, host='127.0.0.1', port=5000)
    except KeyboardInterrupt:
        print("\nServidor encerrado")
        mumble.monitoring_active = False
