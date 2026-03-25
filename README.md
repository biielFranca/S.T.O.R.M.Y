<div align="center">

# ⛈️ S.T.O.R.M.Y

### **System Total Orchestrated Reasoning Multimodal Yoked**

Assistente pessoal de IA híbrida local+cloud com personalidade própria.
Controla seu PC, música, busca dados em tempo real, analisa a tela e aprende com você — tudo em português brasileiro.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Status-Em%20Desenvolvimento-yellow?style=for-the-badge)
![License](https://img.shields.io/badge/Licença-MIT-green?style=for-the-badge)
![LM Studio](https://img.shields.io/badge/LM%20Studio-Vulkan%20%7C%20ROCm-blueviolet?style=for-the-badge)

</div>

---

## 📖 Sobre

**S.T.O.R.M.Y** é uma assistente pessoal de IA que roda localmente no seu PC com suporte a cloud quando necessário. Ela tem personalidade própria — fala em português brasileiro informal com gírias de SP — e foi projetada pra ser sua parceira no dia a dia: controla o Spotify, automatiza tarefas no PC, analisa sua tela em tempo real, busca informações na web e aprende com você.

O diferencial é o **sistema híbrido inteligente**: um classificador de 3 camadas decide automaticamente se a resposta vem do modelo local (LM Studio, sem internet) ou da Claude API (para dados externos), garantindo velocidade máxima sem sacrificar qualidade.

---

## ⚡ Funcionalidades (Fase 1 — Concluída)

### 💬 Conversa e Roteamento Inteligente

- Chat híbrido: **LM Studio local** (sem internet) + **Claude API** (dados externos)
- Classificador inteligente de **3 camadas** que decide automaticamente qual engine usar
- Roteamento **sem latência** para comandos diretos (Spotify, PC, etc.)
- Personalidade consistente: tom informal, gírias de SP, sem markdown nas respostas

### 🎵 Spotify

- Tocar música por **nome, artista ou gênero** com detecção de artistas ambíguos
- Controles: pausar, continuar, próxima, anterior, volume
- **Fila de reprodução**, playlists e transfer entre devices
- Abre o Spotify **automaticamente** se estiver fechado
- Detecta pedidos complexos e executa **múltiplas ações em sequência**

### 🖥️ Controle do PC

- Clicar em elementos pela **descrição visual**
- Digitar texto, pressionar teclas, atalhos, scroll, arrastar
- Abrir **apps e sites** por comando de voz/texto
- **Aprender** novos apps, sites e tarefas personalizadas

### 👁️ Visão Computacional

- Análise contínua da tela via **Qwen2.5-VL** no LM Studio (Vulkan/ROCm)
- Detecta qual app está aberto e o contexto atual
- Encontra elementos visuais por descrição e **clica neles**
- Modo foco com modelo maior para tarefas que exigem precisão

### 🌐 Dados Externos

- Busca web via **Brave Search API**
- Clima em qualquer cidade ou bairro via **Open-Meteo** (sem API key)
- Futebol: tabela, resultados, artilharia, notícias e agenda via **ESPN API** (não oficial)

### 🧠 Memória e Infraestrutura

- **SQLite** local para persistência
- **Sync Supabase** entre devices
- Auto-gerenciamento: salva API keys e edita o próprio código (com confirmação)
- Busca **APIs públicas e ocultas** automaticamente

### 🎮 Hardware

- Suporte ao volante **Logitech G29**: leitura de pedais, marcha e botões
- Mapeamento customizado por jogo (mesmo sem suporte nativo)

---

## 🗺️ Roadmap

| Fase | Status | Descrição |
|------|--------|-----------|
| **Fase 1** | ✅ Concluída | Chat híbrido, Spotify, controle do PC, visão computacional, dados externos, memória |
| **Fase 2** | 🔄 Em andamento | Serviço background Windows, app Android (Kotlin), WhatsApp, handoff entre devices, OpenFinance via Pluggy |
| **Fase 3** | 📋 Planejada | Wake word, Whisper STT local, TTS com clone de voz, bot Discord, orbe visual |
| **Fase 4** | 📋 Planejada | Autonomia total PC e Android, casa inteligente (AC Elgin, TV Samsung, PS5), gestos via webcam, geração de imagens e vídeo |
| **Fase 5** | 📋 Planejada | RAG local ChromaDB, 70+ APIs integradas, financeiro pessoal, saúde e rotina, veículo OBD2 |

---

## 🛠️ Stack Tecnológica

| Categoria | Tecnologias |
|-----------|-------------|
| **Linguagem** | Python 3.12 |
| **IA Local** | LM Studio (Vulkan/ROCm), Ollama, Qwen2.5-VL |
| **IA Cloud** | Claude API (Anthropic) |
| **Banco de Dados** | SQLite (local), Supabase (sync cloud) |
| **APIs Externas** | Brave Search, ESPN API, Open-Meteo, Spotify Web API |
| **Automação** | pyautogui, pygame |
| **Hardware** | Logitech G29 (via pygame) |

---

## 📁 Estrutura do Projeto

```
S.T.O.R.M.Y/
├── main.py                 # Entry point — inicia a S.T.O.R.M.Y
├── agent.py                # Roteador principal e personalidade
├── tools.py                # 16+ ferramentas disponíveis
├── screen_watcher.py       # Visão computacional (Qwen2.5-VL)
├── spotify_controller.py   # OAuth2 e controle do Spotify
├── pc_control.py           # Automação do PC (pyautogui)
├── memory.py               # Memória: RAM + SQLite + Supabase
├── weather.py              # Clima via Open-Meteo
├── sports.py               # Futebol via ESPN API
├── search.py               # Busca web via Brave Search
├── .env                    # Variáveis de ambiente (não commitado)
└── requirements.txt        # Dependências Python
```

---

## 🚀 Como Rodar

### Pré-requisitos

- **Python 3.12+**
- **LM Studio** com Vulkan ou ROCm
- Conta no **Spotify Developer** (para controle de música)
- API keys: Anthropic, Brave Search, Supabase

### Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/biielfranca/S.T.O.R.M.Y.git
cd S.T.O.R.M.Y

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com suas keys (veja a seção abaixo)

# 5. Inicie o LM Studio
# Carregue o modelo desejado e inicie o servidor na porta 1234

# 6. Rode a S.T.O.R.M.Y
python main.py
```

---

## 🔑 Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
# Anthropic (Claude API)
ANTHROPIC_API_KEY=sua_key_aqui

# Brave Search
BRAVE_API_KEY=sua_key_aqui

# Supabase (sync entre devices)
SUPABASE_URL=sua_url_aqui
SUPABASE_KEY=sua_key_aqui

# Spotify
SPOTIFY_CLIENT_ID=seu_client_id_aqui
SPOTIFY_CLIENT_SECRET=seu_client_secret_aqui
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
```

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests.

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/minha-feature`)
3. Commit suas mudanças (`git commit -m 'feat: minha nova feature'`)
4. Push para a branch (`git push origin feature/minha-feature`)
5. Abra um Pull Request

---

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.

---

<div align="center">

Feito com ☕ e muito código por **[@biielfranca](https://github.com/biielfranca)**

</div>
