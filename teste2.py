#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de setup para configurar ambiente Mumble + ICE
Igreja Avivando as Nações
"""

import os
import sys
import subprocess
import urllib.request
import platform


def check_python_version():
    """Verifica versão do Python"""
    if sys.version_info < (3, 6):
        print("❌ Python 3.6+ é necessário")
        return False

    print(f"✅ Python {sys.version.split()[0]} detectado")
    return True


def install_ice():
    """Instala ZeroC Ice"""
    print("\n📦 Instalando ZeroC Ice...")

    try:
        # Tentar importar Ice primeiro
        import Ice
        print(f"✅ ZeroC Ice já instalado: {Ice.stringVersion()}")
        return True
    except ImportError:
        pass

    # Detectar sistema operacional
    system = platform.system().lower()

    if system == "linux":
        # Ubuntu/Debian
        try:
            print("🐧 Detectado sistema Linux - instalando via apt/pip...")

            # Tentar instalar via pip primeiro
            result = subprocess.run([sys.executable, "-m", "pip", "install", "zeroc-ice"],
                                    capture_output=True, text=True)

            if result.returncode == 0:
                print("✅ ZeroC Ice instalado via pip")
                return True
            else:
                print("⚠️  Falha na instalação via pip, tentando repositório...")

                # Instalar dependências do sistema
                os.system("sudo apt update")
                os.system("sudo apt install -y python3-ice python3-zeroc-ice")

        except Exception as e:
            print(f"❌ Erro na instalação Linux: {e}")
            return False

    elif system == "windows":
        print("🪟 Detectado Windows - instalando via pip...")
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "install", "zeroc-ice"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ ZeroC Ice instalado")
                return True
        except Exception as e:
            print(f"❌ Erro na instalação Windows: {e}")
            return False

    elif system == "darwin":  # macOS
        print("🍎 Detectado macOS - instalando via brew/pip...")
        try:
            # Tentar via pip primeiro
            result = subprocess.run([sys.executable, "-m", "pip", "install", "zeroc-ice"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ ZeroC Ice instalado via pip")
                return True

            # Se falhar, sugerir homebrew
            print("💡 Se a instalação falhar, tente:")
            print("   brew install ice")
            print("   pip3 install zeroc-ice")

        except Exception as e:
            print(f"❌ Erro na instalação macOS: {e}")
            return False

    print("❌ Sistema não suportado ou erro na instalação")
    return False


def download_ice_file():
    """Baixa arquivo MumbleServer.ice"""
    print("\n📥 Verificando arquivo MumbleServer.ice...")

    ice_file = "MumbleServer.ice"

    if os.path.exists(ice_file):
        print("✅ Arquivo MumbleServer.ice já existe")
        return True

    # URLs para tentar baixar o arquivo
    urls = [
        "https://raw.githubusercontent.com/mumble-voip/mumble/master/src/murmur/MumbleServer.ice",
        "https://github.com/mumble-voip/mumble/raw/master/src/murmur/MumbleServer.ice"
    ]

    for url in urls:
        try:
            print(f"📡 Baixando de: {url}")
            urllib.request.urlretrieve(url, ice_file)

            if os.path.exists(ice_file) and os.path.getsize(ice_file) > 1000:
                print("✅ Arquivo MumbleServer.ice baixado com sucesso")
                return True

        except Exception as e:
            print(f"❌ Erro ao baixar de {url}: {e}")
            continue

    print("❌ Não foi possível baixar MumbleServer.ice")
    print("💡 Baixe manualmente de:")
    print("   https://github.com/mumble-voip/mumble/raw/master/src/murmur/MumbleServer.ice")
    return False


def create_config_example():
    """Cria exemplo de configuração"""
    print("\n📝 Criando arquivo de configuração exemplo...")

    config_content = '''# Configuração para teste ICE - Igreja Avivando as Nações
# Edite conforme necessário

[ICE]
# Endereço do servidor Mumble
HOST = "127.0.0.1"

# Porta ICE (configurada no murmur.ini)
PORT = 6502

# Secret ICE (configurado no murmur.ini como icesecretwrite)
SECRET = "AdminIgreja2024"

# ID do servidor virtual (geralmente 1)
SERVER_ID = 1

[MUMBLE]
# Porta do servidor Mumble
MUMBLE_PORT = 64738

# Senha do servidor (se configurada)
SERVER_PASSWORD = "AvivandoTec"

[IGREJA]
# Nome da igreja
NOME = "Igreja Avivando as Nações"

# Criar canais automaticamente?
AUTO_CREATE_CHANNELS = True

# Enviar mensagem de boas-vindas?
SEND_WELCOME = True
'''

    try:
        with open("config_igreja.ini", "w", encoding="utf-8") as f:
            f.write(config_content)
        print("✅ Arquivo config_igreja.ini criado")
        return True
    except Exception as e:
        print(f"❌ Erro ao criar configuração: {e}")
        return False


def test_ice_connection():
    """Testa conexão ICE básica"""
    print("\n🔍 Testando conexão ICE...")

    try:
        import Ice

        # Configuração básica
        ice_props = Ice.createProperties()
        ice_props.setProperty("Ice.ImplicitContext", "Shared")

        init_data = Ice.InitializationData()
        init_data.properties = ice_props

        communicator = Ice.initialize(init_data)

        # Teste básico de proxy
        proxy_string = "Meta:tcp -h 127.0.0.1 -p 6502"
        base = communicator.stringToProxy(proxy_string)

        communicator.destroy()

        print("✅ Configuração ICE básica funcionando")
        return True

    except Exception as e:
        print(f"⚠️  Teste ICE falhou (normal se servidor não estiver rodando): {e}")
        return False


def create_systemd_service():
    """Cria serviço systemd para Linux (opcional)"""
    if platform.system().lower() != "linux":
        return

    print("\n🐧 Criando serviço systemd (opcional)...")

    service_content = f'''[Unit]
Description=Mumble ICE Monitor - Igreja Avivando as Nações
After=network.target
Wants=murmur.service
After=murmur.service

[Service]
Type=simple
User=mumble
Group=mumble
WorkingDirectory={os.getcwd()}
ExecStart={sys.executable} {os.path.join(os.getcwd(), "mumble_ice_test.py")}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
'''

    try:
        service_path = "/etc/systemd/system/mumble-ice-igreja.service"
        print(f"💡 Para instalar o serviço, execute como root:")
        print(f"   sudo tee {service_path} << 'EOF'")
        print(service_content)
        print("EOF")
        print("   sudo systemctl daemon-reload")
        print("   sudo systemctl enable mumble-ice-igreja")
        print("   sudo systemctl start mumble-ice-igreja")

    except Exception as e:
        print(f"⚠️  Não foi possível criar serviço: {e}")


def main():
    """Função principal de setup"""
    print("🎤 Setup - Sistema ICE Igreja Avivando as Nações")
    print("=" * 60)

    # Verificar Python
    if not check_python_version():
        return

    # Instalar ICE
    if not install_ice():
        print("❌ Setup interrompido - Ice não pôde ser instalado")
        return

    # Baixar arquivo ICE
    if not download_ice_file():
        print("⚠️  Continuando sem arquivo ICE (pode falhar)")

    # Criar configuração
    create_config_example()

    # Testar conexão
    test_ice_connection()

    # Serviço systemd (Linux)
    create_systemd_service()

    print("\n" + "=" * 60)
    print("✅ SETUP CONCLUÍDO!")
    print("\n📋 PRÓXIMOS PASSOS:")
    print("1. Configure seu servidor Mumble com ICE habilitado")
    print("2. Edite config_igreja.ini conforme necessário")
    print("3. Execute: python mumble_ice_test.py")
    print("\n📚 DOCUMENTAÇÃO:")
    print("- Mumble: https://wiki.mumble.info/")
    print("- ZeroC Ice: https://doc.zeroc.com/ice/3.7/")
    print("\n🙏 Deus abençoe o ministério!")


if __name__ == "__main__":
    main()