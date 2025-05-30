import sys
import Ice
import MumbleServer


def create_church_channels(server):
    """
    Cria uma estrutura de canais organizados para a Igreja Avivando as Nações
    """
    try:
        # Obter o canal raiz (ID 0)
        root_channel = server.getChannelState(0)

        # Estrutura de canais para a igreja
        channels_structure = {
            "Liderança": {
                "description": "Canal para liderança da igreja",
                "subchannels": {
                    "Pastores": "Canal exclusivo dos pastores",
                    "Diáconos": "Canal dos diáconos",
                    "Líderes de Ministério": "Canal para líderes de ministérios"
                }
            },
            "Ministérios": {
                "description": "Canais dos ministérios da igreja",
                "subchannels": {
                    "Louvor": "Canal do ministério de louvor",
                    "Jovens": "Canal do ministério jovem",
                    "Crianças": "Canal do ministério infantil",
                    "Som e Mídia": "Canal da equipe técnica",
                    "Intercessão": "Canal do ministério de intercessão"
                }
            },
            "Departamentos": {
                "description": "Canais administrativos",
                "subchannels": {
                    "Administração": "Canal administrativo",
                    "Secretaria": "Canal da secretaria",
                    "Tesouraria": "Canal financeiro"
                }
            },
            "Eventos": {
                "description": "Canais para eventos especiais",
                "subchannels": {
                    "Cultos Especiais": "Canal para organização de cultos especiais",
                    "Retiros": "Canal para organização de retiros",
                    "Conferências": "Canal para conferências"
                }
            },
            "Geral": {
                "description": "Canais de uso geral",
                "subchannels": {
                    "Sala de Espera": "Canal para aguardar atendimento",
                    "Coordenação Geral": "Canal de coordenação durante eventos"
                }
            }
        }

        created_channels = {}

        # Criar canais principais
        for main_channel_name, main_channel_info in channels_structure.items():
            print(f"Criando canal principal: {main_channel_name}")

            # Criar o canal principal
            main_channel_id = create_channel(
                server,
                main_channel_name,
                main_channel_info["description"],
                parent_id=0
            )

            if main_channel_id:
                created_channels[main_channel_name] = {
                    'id': main_channel_id,
                    'subchannels': {}
                }

                # Criar subcanais
                for subchannel_name, subchannel_desc in main_channel_info["subchannels"].items():
                    print(f"  Criando subcanal: {subchannel_name}")

                    subchannel_id = create_channel(
                        server,
                        subchannel_name,
                        subchannel_desc,
                        parent_id=main_channel_id
                    )

                    if subchannel_id:
                        created_channels[main_channel_name]['subchannels'][subchannel_name] = subchannel_id

        return created_channels

    except Exception as e:
        print(f"Erro ao criar estrutura de canais: {e}")
        return None


def create_channel(server, name, description="", parent_id=0, temporary=False):
    """
    Cria um canal individual no servidor Mumble

    Args:
        server: Instância do servidor Mumble
        name: Nome do canal
        description: Descrição do canal
        parent_id: ID do canal pai (0 para canal raiz)
        temporary: Se o canal é temporário

    Returns:
        int: ID do canal criado ou None se houver erro
    """
    try:
        print(f"Tentando criar canal '{name}' no parent {parent_id}...")

        # Método principal: Usar addChannel
        new_channel_id = server.addChannel(name, parent_id)
        print(f"Canal '{name}' criado com ID: {new_channel_id}")

        # Definir descrição se fornecida
        if description:
            try:
                channel_state = server.getChannelState(new_channel_id)
                channel_state.description = description
                server.setChannelState(channel_state)
                print(f"Descrição definida para canal '{name}'")
            except Exception as desc_error:
                print(f"Aviso: Não foi possível definir descrição: {desc_error}")

        return new_channel_id

    except Exception as e:
        print(f"Erro ao criar canal '{name}': {e}")
        return None


def list_existing_channels(server):
    """
    Lista todos os canais existentes no servidor
    """
    try:
        print("\n=== CANAIS EXISTENTES ===")

        # Obter todos os canais
        all_channels = server.getChannels()

        # Organizar canais por hierarquia
        channels_by_parent = {}
        root_channels = []

        for channel_id, channel_state in all_channels.items():
            if channel_state.parent == 0:
                root_channels.append((channel_id, channel_state))
            else:
                if channel_state.parent not in channels_by_parent:
                    channels_by_parent[channel_state.parent] = []
                channels_by_parent[channel_state.parent].append((channel_id, channel_state))

        # Exibir canais raiz
        for channel_id, channel_state in sorted(root_channels, key=lambda x: x[1].name):
            print(f"[{channel_id}] {channel_state.name}")
            if channel_state.description:
                print(f"    Descrição: {channel_state.description}")

            # Exibir subcanais
            if channel_id in channels_by_parent:
                for sub_id, sub_state in sorted(channels_by_parent[channel_id], key=lambda x: x[1].name):
                    print(f"  └─ [{sub_id}] {sub_state.name}")
                    if sub_state.description:
                        print(f"      Descrição: {sub_state.description}")

        return all_channels

    except Exception as e:
        print(f"Erro ao listar canais: {e}")
        return None


def delete_channel(server, channel_id):
    """
    Remove um canal do servidor
    """
    try:
        server.removeChannel(channel_id)
        print(f"Canal ID {channel_id} removido com sucesso")
        return True
    except Exception as e:
        print(f"Erro ao remover canal ID {channel_id}: {e}")
        return False


def debug_server_methods(server):
    """
    Lista todos os métodos disponíveis no servidor para debug
    """
    print("\n=== MÉTODOS DISPONÍVEIS NO SERVIDOR ===")
    methods = [method for method in dir(server) if not method.startswith('_')]
    for method in sorted(methods):
        print(f"  {method}")
    print("=" * 40)


def setup_ice_authentication(communicator, secret):
    """
    Configura a autenticação ICE adequadamente
    """
    try:
        # Método 1: Configurar contexto implícito
        ic = communicator.getImplicitContext()
        if ic:
            ic.put("secret", secret)
            print(f"Contexto implícito configurado com secret")
            return True
    except Exception as e:
        print(f"Erro ao configurar contexto implícito: {e}")

    return False


def test_permissions(server):
    """
    Testa diferentes operações para verificar permissões
    """
    print("\n=== TESTE DE PERMISSÕES ===")

    try:
        # Teste 1: Listar canais
        channels = server.getChannels()
        print(f"✓ Consegue listar canais: {len(channels)} encontrados")

        # Teste 2: Obter configurações
        try:
            conf = server.getAllConf()
            print("✓ Consegue obter configurações do servidor")
        except Exception as e:
            print(f"✗ Não consegue obter configurações: {e}")

        # Teste 3: Tentar criar canal de teste
        try:
            test_id = server.addChannel("TESTE_PERMISSAO", 0)
            print(f"✓ Consegue criar canais: canal teste criado com ID {test_id}")

            # Remover canal de teste
            try:
                server.removeChannel(test_id)
                print("✓ Consegue remover canais: canal teste removido")
            except Exception as e:
                print(f"✗ Não consegue remover canais: {e}")

        except Exception as e:
            print(f"✗ Não consegue criar canais: {e}")

    except Exception as e:
        print(f"✗ Erro geral de permissões: {e}")


def main():
    # Configurar propriedades ICE para autenticação
    init_data = Ice.InitializationData()
    init_data.properties = Ice.createProperties(sys.argv)

    # CORREÇÃO: Configurações ICE mais específicas
    init_data.properties.setProperty("Ice.ImplicitContext", "Shared")
    init_data.properties.setProperty("Ice.Default.EncodingVersion", "1.0")

    # Configurações de timeout mais generosas
    init_data.properties.setProperty("Ice.Override.Timeout", "60000")
    init_data.properties.setProperty("Ice.Override.ConnectTimeout", "30000")

    with Ice.initialize(sys.argv, init_data) as communicator:
        try:
            # Secret que deve corresponder ao icesecretwrite no murmur.ini
            SECRET = "AdminIgreja2024"

            # Configurar autenticação
            setup_ice_authentication(communicator, SECRET)

            # Conectar ao servidor Mumble usando as configurações do murmur.ini
            proxy_string = "Meta:tcp -h 127.0.0.1 -p 6502 -t 60000"
            base = communicator.stringToProxy(proxy_string)

            # CORREÇÃO: Definir secret no contexto da conexão
            ctx = {"secret": SECRET}
            meta = MumbleServer.MetaPrx.checkedCast(base, ctx)

            if meta is None:
                print("Erro: Não foi possível conectar ao servidor Mumble")
                print("Verifique se:")
                print("1. O servidor Mumble está rodando")
                print("2. As configurações ICE estão corretas no murmur.ini")
                print("3. A porta 6502 está acessível")
                print("4. O icesecretwrite está configurado como 'AdminIgreja2024'")
                return

            print("Conectado ao Meta servidor...")

            # Obter o primeiro servidor disponível
            servers = meta.getAllServers(ctx)
            if not servers:
                print("Nenhum servidor encontrado")
                return

            server = servers[0]  # Usar o primeiro servidor

            if not server.isRunning(ctx):
                print("Servidor não está rodando - tentando iniciar...")
                try:
                    server.start(ctx)
                    print("Servidor iniciado com sucesso")
                except Exception as start_error:
                    print(f"Erro ao iniciar servidor: {start_error}")
                    return

            print(f"Conectado ao servidor ID {server.id(ctx)}")

            # IMPORTANTE: Usar contexto em todas as operações
            def server_with_context(method_name):
                """Wrapper para automaticamente passar o contexto de autenticação"""

                def wrapper(*args, **kwargs):
                    method = getattr(server, method_name)
                    return method(*args, ctx, **kwargs)

                return wrapper

            # Criar wrapper para métodos principais
            server_methods = {
                'getChannels': lambda: server.getChannels(ctx),
                'addChannel': lambda name, parent: server.addChannel(name, parent, ctx),
                'removeChannel': lambda channel_id: server.removeChannel(channel_id, ctx),
                'getChannelState': lambda channel_id: server.getChannelState(channel_id, ctx),
                'setChannelState': lambda channel_state: server.setChannelState(channel_state, ctx),
                'getAllConf': lambda: server.getAllConf(ctx)
            }

            # Testar permissões iniciais
            try:
                channels = server_methods['getChannels']()
                print(f"Servidor tem {len(channels)} canais existentes")
            except Exception as perm_error:
                print(f"Erro de permissão: {perm_error}")
                print("Verificar se o secret está correto no murmur.ini")
                return

            # Menu de opções
            while True:
                print("\n=== GERENCIADOR DE CANAIS - IGREJA AVIVANDO AS NAÇÕES ===")
                print("1. Listar canais existentes")
                print("2. Criar estrutura completa de canais da igreja")
                print("3. Criar canal individual")
                print("4. Remover canal")
                print("5. Debug - Listar métodos do servidor")
                print("6. Testar permissões")
                print("7. Sair")

                choice = input("\nEscolha uma opção: ").strip()

                if choice == "1":
                    list_existing_channels_with_context(server, ctx)

                elif choice == "2":
                    print("\nCriando estrutura completa de canais...")
                    created = create_church_channels_with_context(server, ctx)
                    if created:
                        print(f"\nEstrutura criada com sucesso! {len(created)} canais principais criados.")
                    else:
                        print("Erro ao criar estrutura de canais")

                elif choice == "3":
                    name = input("Nome do canal: ").strip()
                    description = input("Descrição (opcional): ").strip()
                    parent_id = input("ID do canal pai (0 para raiz): ").strip()

                    try:
                        parent_id = int(parent_id) if parent_id else 0
                        channel_id = create_channel_with_context(server, ctx, name, description, parent_id)
                        if channel_id:
                            print(f"Canal criado com sucesso! ID: {channel_id}")
                    except ValueError:
                        print("ID do canal pai deve ser um número")

                elif choice == "4":
                    try:
                        channel_id = int(input("ID do canal para remover: ").strip())
                        if channel_id == 0:
                            print("Não é possível remover o canal raiz")
                        else:
                            delete_channel_with_context(server, ctx, channel_id)
                    except ValueError:
                        print("ID deve ser um número")

                elif choice == "5":
                    debug_server_methods(server)

                elif choice == "6":
                    test_permissions_with_context(server, ctx)

                elif choice == "7":
                    print("Saindo...")
                    break

                else:
                    print("Opção inválida")

        except Exception as e:
            print(f"Erro na conexão: {e}")
            print("Verifique se o servidor Mumble está rodando e se as configurações ICE estão corretas")


# Versões das funções que usam contexto ICE
def create_channel_with_context(server, ctx, name, description="", parent_id=0, temporary=False):
    """
    Cria um canal individual no servidor Mumble usando contexto ICE
    """
    try:
        print(f"Tentando criar canal '{name}' no parent {parent_id}...")

        new_channel_id = server.addChannel(name, parent_id, ctx)
        print(f"Canal '{name}' criado com ID: {new_channel_id}")

        # Definir descrição se fornecida
        if description:
            try:
                channel_state = server.getChannelState(new_channel_id, ctx)
                channel_state.description = description
                server.setChannelState(channel_state, ctx)
                print(f"Descrição definida para canal '{name}'")
            except Exception as desc_error:
                print(f"Aviso: Não foi possível definir descrição: {desc_error}")

        return new_channel_id

    except Exception as e:
        print(f"Erro ao criar canal '{name}': {e}")
        return None


def list_existing_channels_with_context(server, ctx):
    """
    Lista todos os canais existentes no servidor usando contexto ICE
    """
    try:
        print("\n=== CANAIS EXISTENTES ===")

        all_channels = server.getChannels(ctx)

        # Organizar canais por hierarquia
        channels_by_parent = {}
        root_channels = []

        for channel_id, channel_state in all_channels.items():
            if channel_state.parent == 0:
                root_channels.append((channel_id, channel_state))
            else:
                if channel_state.parent not in channels_by_parent:
                    channels_by_parent[channel_state.parent] = []
                channels_by_parent[channel_state.parent].append((channel_id, channel_state))

        # Exibir canais raiz
        for channel_id, channel_state in sorted(root_channels, key=lambda x: x[1].name):
            print(f"[{channel_id}] {channel_state.name}")
            if channel_state.description:
                print(f"    Descrição: {channel_state.description}")

            # Exibir subcanais
            if channel_id in channels_by_parent:
                for sub_id, sub_state in sorted(channels_by_parent[channel_id], key=lambda x: x[1].name):
                    print(f"  └─ [{sub_id}] {sub_state.name}")
                    if sub_state.description:
                        print(f"      Descrição: {sub_state.description}")

        return all_channels

    except Exception as e:
        print(f"Erro ao listar canais: {e}")
        return None


def delete_channel_with_context(server, ctx, channel_id):
    """
    Remove um canal do servidor usando contexto ICE
    """
    try:
        server.removeChannel(channel_id, ctx)
        print(f"Canal ID {channel_id} removido com sucesso")
        return True
    except Exception as e:
        print(f"Erro ao remover canal ID {channel_id}: {e}")
        return False


def create_church_channels_with_context(server, ctx):
    """
    Cria estrutura completa usando contexto ICE
    """
    try:
        # Estrutura de canais para a igreja
        channels_structure = {
            "Liderança": {
                "description": "Canal para liderança da igreja",
                "subchannels": {
                    "Pastores": "Canal exclusivo dos pastores",
                    "Diáconos": "Canal dos diáconos",
                    "Líderes de Ministério": "Canal para líderes de ministérios"
                }
            },
            "Ministérios": {
                "description": "Canais dos ministérios da igreja",
                "subchannels": {
                    "Louvor": "Canal do ministério de louvor",
                    "Jovens": "Canal do ministério jovem",
                    "Crianças": "Canal do ministério infantil",
                    "Som e Mídia": "Canal da equipe técnica",
                    "Intercessão": "Canal do ministério de intercessão"
                }
            },
            "Departamentos": {
                "description": "Canais administrativos",
                "subchannels": {
                    "Administração": "Canal administrativo",
                    "Secretaria": "Canal da secretaria",
                    "Tesouraria": "Canal financeiro"
                }
            },
            "Eventos": {
                "description": "Canais para eventos especiais",
                "subchannels": {
                    "Cultos Especiais": "Canal para organização de cultos especiais",
                    "Retiros": "Canal para organização de retiros",
                    "Conferências": "Canal para conferências"
                }
            },
            "Geral": {
                "description": "Canais de uso geral",
                "subchannels": {
                    "Sala de Espera": "Canal para aguardar atendimento",
                    "Coordenação Geral": "Canal de coordenação durante eventos"
                }
            }
        }

        created_channels = {}

        # Criar canais principais
        for main_channel_name, main_channel_info in channels_structure.items():
            print(f"Criando canal principal: {main_channel_name}")

            main_channel_id = create_channel_with_context(
                server, ctx,
                main_channel_name,
                main_channel_info["description"],
                parent_id=0
            )

            if main_channel_id:
                created_channels[main_channel_name] = {
                    'id': main_channel_id,
                    'subchannels': {}
                }

                # Criar subcanais
                for subchannel_name, subchannel_desc in main_channel_info["subchannels"].items():
                    print(f"  Criando subcanal: {subchannel_name}")

                    subchannel_id = create_channel_with_context(
                        server, ctx,
                        subchannel_name,
                        subchannel_desc,
                        parent_id=main_channel_id
                    )

                    if subchannel_id:
                        created_channels[main_channel_name]['subchannels'][subchannel_name] = subchannel_id

        return created_channels

    except Exception as e:
        print(f"Erro ao criar estrutura de canais: {e}")
        return None


def test_permissions_with_context(server, ctx):
    """
    Testa permissões usando contexto ICE
    """
    print("\n=== TESTE DE PERMISSÕES ===")

    try:
        # Teste 1: Listar canais
        channels = server.getChannels(ctx)
        print(f"✓ Consegue listar canais: {len(channels)} encontrados")

        # Teste 2: Obter configurações
        try:
            conf = server.getAllConf(ctx)
            print("✓ Consegue obter configurações do servidor")
        except Exception as e:
            print(f"✗ Não consegue obter configurações: {e}")

        # Teste 3: Tentar criar canal de teste
        try:
            test_id = server.addChannel("TESTE_PERMISSAO", 0, ctx)
            print(f"✓ Consegue criar canais: canal teste criado com ID {test_id}")

            # Remover canal de teste
            try:
                server.removeChannel(test_id, ctx)
                print("✓ Consegue remover canais: canal teste removido")
            except Exception as e:
                print(f"✗ Não consegue remover canais: {e}")

        except Exception as e:
            print(f"✗ Não consegue criar canais: {e}")

    except Exception as e:
        print(f"✗ Erro geral de permissões: {e}")


if __name__ == "__main__":
    main()