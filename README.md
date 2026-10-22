# AutoClip Studio — Podcast Clipper

**Automatiza a extração de clipes curtos (Shorts/Reels/TikTok) e cortes longos (16:9) de podcasts no YouTube** com transcrição, seleção inteligente via IA (Gemini) ou heurísticas estatísticas, enquadramento facial, legendas dinâmicas e metadados prontos para publicação.

---

## ✨ Funcionalidades Principais

| Recurso | Descrição |
|---------|-----------|
| **🎬 Shorts Verticais 9:16** | Corte com tracking facial (MediaPipe), split-screen dinâmico para 2 pessoas, vignette, legendas animadas palavra-por-palavra |
| **📺 Cortes Longos 16:9** | Vídeos horizontais para YouTube tradicional, remoção inteligente de silêncios (jump cut FFmpeg), overlay opcional |
| **⏱️ Apenas Timestamps** | Modo ultra-rápido: calcula pontos de corte + metadados IA sem renderizar vídeo |
| **🤖 IA Gemini (Recomendado)** | Análise semântica da transcrição completa: detecta hooks, viradas de raciocínio, conclusões e momentos virais |
| **📊 Heurísticas & Heatmap** | Estatísticas clássicas: palavras de atenção, contraste, perguntas, pausas, picos de audiência do YouTube ("mais reproduzido") |
| **🎵 3 Modos de Transcrição** | 1) Legendas YouTube Parcial (muito lento, mas consome menos banda)<br>2) Legendas YouTube Completo (balanceado)<br>3) Whisper Local (alta precisão, offline) |
| **🔤 Legendas Premium** | Re-transcrição com Whisper apenas nos cortes finais → sincronização milimétrica palavra-por-palavra |
| **📦 Metadados Automáticos** | Título viral, descrição otimizada, hashtags e *hook* de abertura via Gemini |
| **🖥️ Interface Desktop (PyWebView)** | Janela nativa Windows, monitoramento em tempo real (stepper, progress, logs coloridos, cancelamento) |
| **📚 Biblioteca de Projetos** | Galeria com players, edição de metadados, cópia one-click, abertura no Explorer/player nativo |

---

## 🏗️ Arquitetura

```
├── src/                          # Python Backend
│   ├── main.py                   # CLI interativo (questionary)
│   ├── core/
│   │   └── pipeline.py           # Engine principal (PipelineEngine, PipelineOptions)
│   ├── domain/segment.py         # Dataclass Segment (start, end, text, norm, score)
│   ├── heuristics/               # 8 heurísticas de pontuação (modulares)
│   ├── services/
│   │   ├── gemini_service.py     # IA para seleção de cortes + metadados
│   │   └── youtube_service.py    # Upload YouTube (opcional)
│   ├── utils/                    # 17 utilitários (download, corte, face, legendas, etc.)
│   └── gui/
│       ├── api.py                # Bridge Python ↔ JS (window.pywebview.api)
│       ├── server.py             # Servidor Bottle local (media streaming + static)
│       ├── app.py                # Entry point PyWebView
│       └── web/                  # Frontend React build servido pelo Bottle
├── client/                       # React + TypeScript + Vite + Tailwind + Shadcn/ui
│   ├── src/components/           # Tabs: ShortsStudio, LongClips, Library, Diagnostic
│   ├── src/hooks/                # useClipperStatus, useMobile
│   ├── src/lib/bridge.ts         # Tipagem TypeScript para window.pywebview.api
│   └── src/types/api.ts          # Tipos compartilhados (PipelineOptions, ClipItem, etc.)
├── models/blaze_face_short_range.tflite   # MediaPipe face detection
├── assets/overlays/              # Overlays 16:9 para clipes longos
├── assets/audios/musics/         # Músicas de fundo para Shorts
├── output/<slug>/clips/          # Saída organizada por projeto
└── docs/                         # Documentação técnica
```

---

## 🚀 Início Rápido

### Pré-requisitos
- **Python 3.12+** (gerenciado via Poetry)
- **FFmpeg** no PATH do sistema
- **Windows 10/11** (interface desktop nativa)
- Chave **Google Gemini API** (obrigatória para IA): <https://aistudio.google.com/>

### Instalação

```bash
# 1. Clone e entre no diretório
cd podcast-clipper

# 2. Instale dependências Python
poetry install

# 3. Configure variáveis de ambiente
cp .env.example .env
# Edite .env e adicione sua GEMINI_API_KEY

# 4. (Opcional) Build do frontend React para produção
cd client && npm install && npm run build && cd ..

# 5. Execute
poetry run gui          # Interface gráfica desktop (recomendado)
# OU
poetry run start        # CLI interativo no terminal
```

> **Nota:** O frontend React roda em desenvolvimento via `npm run dev` (porta 5173) com HMR. Configure `VITE_DEV_URL=http://localhost:5173` no `.env` para usar o dev server dentro do PyWebView.

---

## 📖 Modos de Operação

### 1. Estúdio de Shorts (9:16) — Vertical
Ideal para **TikTok, YouTube Shorts, Instagram Reels**.

| Opção | Efeito |
|-------|--------|
| **IA Gemini** | Seleção semântica dos melhores *hooks* e momentos virais |
| **Heurísticas + Heatmap** | Pontuação estatística + picos de retenção do YouTube |
| **Legendas YouTube (Parcial)** | 🐢 Muito lento, mas consome menos banda — baixa só os trechos dos cortes (30–90s cada) |
| **Legendas YouTube (Completo)** | ⚖️ Baixa vídeo 720p completo + legendas oficiais |
| **Whisper Local** | 🎯 Alta precisão — ideal para vídeos sem legendas ou auto-geradas ruins |
| **Re-transcrever com Whisper** | ✍️ Sincronização perfeita palavra-por-palavra nas legendas queimadas |
| **Split-Screen 2 Pessoas** | 👥 Divide tela em 2 blocos verticais quando detecta 2 rostos (MediaPipe) |
| **Vignette** | 🎞️ Escurece bordas para foco no centro (PI/4, PI/5, PI/3.5) |

### 2. Cortes Longos (16:9) — Horizontal
Ideal para **YouTube tradicional, cortes de debate, entrevistas 3–20 min**.

| Parâmetro | Descrição |
|-----------|-----------|
| **IA Gemini** | Identifica tópicos fechados (pergunta → resposta completa) |
| **Intervalo Personalizado** | Início/fim manual (`HH:MM:SS`) |
| **Duração Mín/Máx** | 2–15 min / 5–20 min |
| **Quantidade de Cortes** | 1–5 blocos temáticos |
| **Remoção de Silêncio (Jump Cut)** | FFmpeg `silenceremove` com presets: Suave (-35dB), Padrão (-30dB), Agressivo (-25dB) |
| **Overlay 16:9** | Moldura/marca d'água opcional (PNG/JPG) |

### 3. Apenas Timestamps & Metadados
⚡ **Ultra-rápido** — sem download/renderização de vídeo. Gera:
- `timestamps.json` / `timestamps.txt` com inícios/fins/durações
- Títulos, descrições, hooks e tags via IA
- Pronto para colar no Premiere, CapCut, DaVinci

---

## 🧠 Pipeline Interno (6 Etapas)

```
1. METADADOS      → yt-dlp: título, thumbnail, duração, canal, views
2. HEATMAP        → yt-dlp: curva "mais reproduzido" do YouTube (opcional)
3. PREPARAÇÃO     → Download completo OU prepara download parcial
4. TRANSCRIÇÃO    → Whisper local OU legendas YouTube (fallback automático)
5. SELEÇÃO        → IA Gemini OU Heurísticas (8 scores) + agrupamento
6. RENDERIZAÇÃO   → FFmpeg/MoviePy: crop 9:16 face-tracking, split-screen,
                    legendas animadas, vignette, jump cut, overlay
```

---

## 🔧 Configuração Avançada (`.env`)

```env
# Obrigatório para IA
GEMINI_API_KEY="sua_chave_aqui"
GEMINI_MODEL="gemini-2.5-flash"           # Modelo principal
GEMINI_FALLBACK_MODELS="gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash"

# Opcionais
VITE_DEV_URL="http://localhost:5173"       # HMR no PyWebView
AUTOCLIP_DEBUG="false"                     # DevTools no PyWebView
DEFAULT_LONG_CLIP_OVERLAY="assets/overlays/frame.png"
# AI_GATEWAY_API_KEY=""                    # Vercel AI Gateway (opcional)
```

---

## 📁 Estrutura de Saída

```
output/
└── meu-podcast-episodio-123/          # slug do vídeo
    ├── segments.json                   # Transcrição completa (Whisper/YT)
    ├── clips.json                      # Plano de cortes (segmentos por clipe)
    ├── timestamps.json                 # Consolidado: inícios, fins, scores, metadados
    ├── timestamps.txt                  # Legível por humanos (para editores)
    └── clips/
        ├── clip_00.mp4                 # Vídeo renderizado
        ├── clip_00_details.json        # Título, descrição, tags, hook, viral_score
        ├── clip_01.mp4
        ├── clip_01_details.json
        └── ...
```

---

## 🛠️ Desenvolvimento

### Backend (Python)
```bash
poetry run python src/main.py          # CLI
poetry run python -m src.gui.app       # GUI direto
poetry run ruff check .                # Lint
poetry run ruff format .               # Format
poetry run pyright                     # Type check
```

### Frontend (React + Vite)
```bash
cd client
npm run dev            # Dev server (HMR) — porta 5173
npm run build          # Build produção → client/dist/
npm run lint           # ESLint + Oxlint
npm run format         # Prettier
```

### Testar a integração PyWebView + React Dev
1. `cp .env.example .env` → adicione `VITE_DEV_URL=http://localhost:5173`
2. Terminal 1: `cd client && npm run dev`
3. Terminal 2: `poetry run gui`

---

## 📚 Documentação Técnica

| Arquivo | Descrição |
|---------|-----------|
| `docs/ARCHITECTURE.md` | Visão geral da arquitetura, fluxo de dados, bridge PyWebView |
| `docs/PIPELINE.md` | Detalhamento das 6 etapas do pipeline, opções, fallbacks |
| `docs/HEURISTICS.md` | 8 heurísticas de pontuação, fórmulas, pesos, anti-heurísticas |
| `docs/GEMINI_SERVICE.md` | Prompts, schemas, fallback models, structured output |
| `docs/VIDEO_PROCESSING.md` | FFmpeg/MoviePy: face tracking, split-screen, legendas, jump cut |
| `docs/FRONTEND.md` | React app: tabs, hooks, bridge types, Shadcn/ui components |
| `docs/CLI.md` | Referência do CLI interativo (questionary) |
| `docs/CONFIG.md` | Todas as variáveis `.env`, presets, modelos suportados |

---

## 🤝 Contribuindo

1. Fork → branch `feat/nova-funcionalidade`
2. Commits convencionais: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
3. `poetry run ruff format . && poetry run ruff check .` antes do PR
4. PR com descrição clara + screenshots se UI

---

## 📄 Licença

MIT — veja `LICENSE`.

---

## 🙏 Créditos

- **MediaPipe** (Google) — face detection `blaze_face_short_range.tflite`
- **Faster-Whisper** — transcrição local otimizada (CTranslate2)
- **Google Gemini** — IA para seleção semântica e metadados
- **yt-dlp** — download e metadados YouTube
- **MoviePy + FFmpeg** — processamento de vídeo
- **React + Tailwind + Shadcn/ui** — frontend moderno
- **PyWebView + Bottle** — desktop bridge nativo