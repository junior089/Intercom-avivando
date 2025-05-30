#!/usr/bin/env python3
"""
Script para testar a configuração do Mumble Server e conectividade
"""

import Ice
import sys
import time
import socket
import subprocess
import os


def test_port_availability(port):
    """Testa se uma porta está disponível"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0  # 0 significa que conectou (porta em uso)
    except:
        return False


def validate_config_file(config_path="murmur.ini"):
    """Valida o arquivo de configuração"""
    print(f"📋 Validando arquivo de configuração: {config_path}")

    if not os.path.exists(config_path):
        print(f"❌ Arquivo não encontrado: {config_path}")
        return False

    required_settings = {
        'ice=': 'Configuração Ice para administração remota',
        'icesecretwrite=': 'Senha para escrita via Ice',
        'port=': 'Porta do servidor Mumble',
        'database=': 'Arquivo de banco de dados'
    }

    found_settings = {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        for setting, description in required_settings.items():
            lines = [line.strip() for line in content.split('\n')
                     if line.strip().startswith(setting) and not line.strip().startswith(';')]

            if lines:
                found_settings[setting] = lines[0]
                print(f"✅ {description}: {lines[0]}")
            else:
                print(f"❌ {description}: NÃO ENCONTRADO")

    except Exception as e:
        print(f"❌ Erro ao ler arquivo: {e}")
        return False

    return len(found_settings) == len(required_settings)


def test_mumble_connectivity():
    """Testa conectividade com o servidor Mumble"""
    print("\n🔌 Testando conectividade com Mumble Server...")

    # Verificar se as portas estão em uso
    ports_to_check = [64738, 6502]  # Mumble e Ice

    for port in ports_to_check:
        if test_port_availability(port):
            if port == 64738:
                print(f"✅ Porta {port} (Mumble Server) está ativa")
            elif port == 6502:
                print(f"✅ Porta {port} (Ice Interface) está ativa")
        else:
            print(f"❌ Porta {port} não está respondendo")
            if port == 64738:
                print("   💡 Execute o Mumble Server primeiro")
            elif port == 6502:
                print("   💡 Verifique a configuração Ice no arquivo .ini")

    # Testar conexão Ice se a porta estiver ativa
    if test_port_availability(6502):
        return test_ice_connection()
    else:
        print("⚠️ Não foi possível testar Ice - servidor não está rodando")
        return False


def test_ice_connection():
    """Testa conexão específica via Ice"""
    communicator = None

    try:
        print("🧊 Testando conexão Ice...")

        # Inicializar Ice
        init_data = Ice.InitializationData()
        init_data.properties = Ice.createProperties()
        init_data.properties.setProperty("Ice.ImplicitContext", "Shared")

        communicator = Ice.initialize(init_data)

        # Tentar conectar
        proxy_string = "Meta:tcp -h 127.0.0.1 -p 6502"
        base_proxy = communicator.stringToProxy(proxy_string)

        # Testar ping básico
        base_proxy.ice_ping()
        print("✅ Ping Ice bem-sucedido!")

        # Tentar importar Murmur
        try:
            import Murmur
            print("✅ Módulo Murmur carregado!")

            # Tentar cast
            meta_proxy = Murmur.MetaPrx.checkedCast(base_proxy)

            if meta_proxy:
                print("✅ Meta proxy conectado!")

                # Obter informações do servidor
                servers = meta_proxy.getBootedServers()
                print(f"📊 Servidores ativos: {len(servers)}")

                if servers:
                    server = servers[0]

                    # Informações básicas
                    try:
                        server_name = server.getConf('servername')
                        max_users = server.getConf('users')
                        port = server.getConf('port')

                        print(f"🏛️ Nome do servidor: {server_name}")
                        print(f"👥 Máximo de usuários: {max_users}")
                        print(f"🔌 Porta: {port}")

                        # Estatísticas atuais
                        users = server.getUsers()
                        channels = server.getChannels()

                        print(f"👤 Usuários conectados: {len(users)}")
                        print(f"📺 Canais existentes: {len(channels)}")

                        # Testar se podemos criar um canal de teste
                        try:
                            test_channel_id = server.addChannel("🧪 TESTE-CONEXAO", 0)
                            print("✅ Permissões de escrita funcionando!")

                            # Remover canal de teste
                            server.removeChannel(test_channel_id)
                            print("✅ Canal de teste removido com sucesso!")

                        except Exception as e:
                            print(f"⚠️ Teste de escrita falhou: {e}")
                            print("💡 Verifique a senha 'icesecretwrite' na configuração")

                        return True

                    except Exception as e:
                        print(f"⚠️ Erro ao obter informações do servidor: {e}")
                        return False
                else:
                    print("❌ Nenhum servidor ativo encontrado")
                    return False
            else:
                print("❌ Falha no cast do Meta proxy")
                return False

        except ImportError:
            print("❌ Módulo Murmur não encontrado!")
            print("💡 Adicione o diretório do Mumble ao PATH do Python")
            return False

    except Ice.ConnectFailedException:
        print("❌ Falha na conexão Ice!")
        print("💡 Verifique se o servidor está rodando e a porta 6502 está aberta")
        return False

    except Exception as e:
        print(f"❌ Erro inesperado na conexão Ice: {e}")
        return False

    finally:
        if communicator:
            communicator.destroy()


def print_next_steps(config_valid, server_running):
    """Mostra próximos passos baseado nos resultados"""
    print("\n" + "=" * 50)
    print("📋 RESUMO E PRÓXIMOS PASSOS")
    print("=" * 50)

    if config_valid and server_running:
        print("🎉 TUDO OK! Sistema pronto para configuração da igreja!")
        print("\n✅ Pode executar agora:")
        print("   python igreja_setup.py --setup")
        print("\n📌 Credenciais configuradas:")
        print("   Senha do servidor: AvivandoTec")
        print("   Porta: 64738")
        print("   Ice admin: AdminIgreja2024")

    elif config_valid and not server_running:
        print("⚠️ Configuração OK, mas servidor não está rodando")
        print("\n🚀 Para iniciar o servidor:")
        print("   1. Abra CMD como Administrador")
        print("   2. Navegue até pasta do Mumble")
        print("   3. Execute: mumble-server.exe -ini mumble-server.ini")

    elif not config_valid:
        print("❌ Problemas na configuração detectados")
        print("\n🔧 Verifique:")
        print("   - Arquivo mumble-server.ini existe")
        print("   - Configurações obrigatórias presentes")
        print("   - Sintaxe correta no arquivo")

    print("\n💡 Para monitoramento contínuo:")
    print("   Execute este script periodicamente para verificar status")


def main():
    """Função principal"""
    print("🔍 DIAGNÓSTICO COMPLETO DO MUMBLE SERVER")
    print("=" * 50)

    # 1. Validar configuração
    config_valid = validate_config_file()

    # 2. Testar conectividade
    server_running = test_mumble_connectivity()

    # 3. Mostrar próximos passos
    print_next_steps(config_valid, server_running)


if __name__ == "__main__":
    main()