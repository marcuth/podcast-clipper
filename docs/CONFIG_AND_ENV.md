# Configuração de Ambiente, Dependências e Estrutura

Este documento consolida os pré-requisitos de sistema, instalação de dependências, variáveis de ambiente, comandos de desenvolvimento e a estrutura do diretório de saída do **AutoClip Studio**.

---

## 1. Pré-requisitos do Sistema

| Componente | Requisito | Notas |
|------------|-----------|-------|
| **Sistema Operacional** | Windows 10/11 | Suporte nativo para janela desktop via `pywebview` |
| **Python** | `>=3.12, <3.13` | Gerenciado via Poetry |
| **Node.js** | `>=18` | Para compilação e desenvolvimento do frontend React |
| **FFmpeg** | Instalado e no PATH | Obrigatório para conversão, corte e junção de vídeos/áudios |
| **Google Gemini API Key** | `GEMINI_API_KEY` | Obrigatória para seleção semântica com IA e geração de metadados |

---

## 2. Instalação Passo a Passo

### 2.1 Dependências Python (Poetry)
```bash
# Na raiz do projeto (podcast-clipper):
poetry install
```

Isso instalará pacotes chave como `faster-whisper`, `moviepy`, `opencv-python`, `mediapipe`, `yt-dlp`, `pywebview`, `bottle`, `ai` e `pydantic`.

### 2.2 Dependências do Frontend (npm)
```bash
cd client
npm install
npm run build
cd ..
```

O comando `npm run build` gera a pasta `client/dist/` (renomeada/copiada para uso do servidor interno Bottle).

---

## 3. Variáveis de Ambiente (`.env`)

Crie um arquivo `.env` na raiz do projeto (baseado em `.env.example`):

```env
# ==============================================================================
# AutoClip Studio — Configurações Principais
# ==============================================================================

# Chave de API da Google Gemini (Obrigatória para IA e metadados)
# Obtenha gratuitamente em: https://aistudio.google.com/
GEMINI_API_KEY="AIzaSy..."

# Modelo principal do Gemini para seleção e metadados
GEMINI_MODEL="gemini-2.5-flash"

# Modelos de fallback/contingência em caso de erro ou cota excedida
GEMINI_FALLBACK_MODELS="gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash"

# (Opcional) Vercel AI Gateway API Key (se utilizar a infraestrutura da Vercel)
# AI_GATEWAY_API_KEY=""

# (Opcional) URL do servidor de desenvolvimento do Vite (para HMR no PyWebView)
# VITE_DEV_URL="http://localhost:5173"

# (Opcional) Ativar DevTools inspecionáveis no PyWebView (true/false)
# AUTOCLIP_DEBUG="false"

# (Opcional) Caminho padrão para imagem de overlay 16:9 em cortes longos
DEFAULT_LONG_CLIP_OVERLAY="assets/overlays/frame.png"
```

---

## 4. Estrutura do Diretório de Saída (`output/`)

Todos os vídeos renderizados, arquivos de transcrição e metadados são salvos em `output/<slug-do-video>/`:

```
output/
└── podcast-episodio-especial/          # Pasta do projeto (slug gerado do título)
    ├── segments.json                   # Transcrição bruta (Whisper ou YouTube Captions)
    ├── clips.json                      # Plano de cortes gerado (segmentos por clipe)
    ├── timestamps.json                 # Consolidado em JSON com inícios, fins e metadados
    ├── timestamps.txt                  # Arquivo resumido para humanos/editores
    └── clips/                          # Pasta contendo os arquivos finais de cada clipe
        ├── clip_00.mp4                 # Vídeo renderizado do Clipe 1
        ├── clip_00_details.json        # Metadados: título, descrição, tags, hook e score
        ├── clip_00.ass                 # Arquivo de legendas animadas ASS (se aplicável)
        ├── clip_01.mp4
        ├── clip_01_details.json
        └── ...
```

---

## 5. Arquivos de Metadados (`_details.json`)

Cada clipe possui um arquivo JSON correspondente contendo as informações para publicação:

```json
{
    "title": "Por que o médico proibiu creatina com café",
    "description": "Neste trecho de PodCast Show no episódio \"Especial Saúde\", o especialista explica por que misturar creatina com café pode prejudicar a absorção. A explicação bioquímica é surpreendente.\n\nVocê costuma tomar creatina com café?",
    "tags": ["shorts", "podcast", "cortes", "creatina", "saude", "suplementos"],
    "viral_score": 9.2,
    "hook": "Meu médico me disse: 'nunca tome creatina com café'"
}
```

Ao editar qualquer informação na aba **Biblioteca de Projetos**, estas alterações são gravadas diretamente no respectivo arquivo `clip_XX_details.json`.

---

## 6. Comandos e Scripts Úteis

### Interface e Pipeline
```bash
poetry run gui         # Inicia a aplicação Desktop nativa (PyWebView)
poetry run start       # Inicia o pipeline interativo no terminal (CLI)
```

### Qualidade de Código (Python)
```bash
poetry run ruff check .   # Executa o linter Ruff
poetry run ruff format .  # Executa o formatador Ruff
poetry run pyright        # Executa a verificação estática de tipos
```

### Qualidade de Código (Frontend)
```bash
cd client
npm run dev               # Inicia servidor Vite com HMR na porta 5173
npm run build             # Compila o frontend para produção
npm run lint              # Executa ESLint + Oxlint
npm run format            # Executa Prettier
```

---

## 7. Solução de Problemas Comuns

| Problema | Causa Provável | Solução |
|----------|────────────────|---------|
| `FFmpeg not found` | FFmpeg não instalado ou ausente no PATH | Baixe o FFmpeg, adicione a pasta `bin` às Variáveis de Ambiente do Windows e reinicie o terminal |
| `GEMINI_API_KEY não encontrada` | Arquivo `.env` ausente ou chave não preenchida | Configure a chave na aba **Diagnóstico** da GUI ou adicione no arquivo `.env` |
| `Face detector model missing` | Modelo MediaPipe não encontrado em `models/` | Verifique se o arquivo `models/blaze_face_short_range.tflite` existe |
| `Legendas do YouTube indisponíveis` | Vídeo sem legendas públicas | O sistema mudará **automaticamente para Whisper local**. Certifique-se de ter conexão para baixar o áudio |
| `Porta 48123 ocupada` | Outra instância em execução | O servidor Bottle detectará a porta ocupada e escolherá uma porta livre automaticamente |
