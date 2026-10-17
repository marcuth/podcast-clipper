# Arquitetura do AutoClip Studio

Visão geral da arquitetura de sistemas, fluxo de dados, componentes e integrações do **AutoClip Studio** (Podcast Clipper).

---

## 1. Visão Geral de Alto Nível

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USUÁRIO (Desktop Windows)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PYWEBVIEW 6.x — Janela Nativa Windows (1320×880, Tema Escuro)              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  FRONTEND REACT + TYPESCRIPT + VITE (servido estaticamente ou HMR)      │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                   │ │
│  │  │ Shorts   │ │ Long     │ │ Library  │ │ Diagnostic│  Abas (Tabs)     │ │
│  │  │ Studio   │ │ Clips    │ │ Clips    │ │           │                   │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘                   │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                      │
│         window.pywebview.api  ◄──────┼──────►  window.__clipperBridge      │
│         (JS → Python calls)          │       (Python → JS events)          │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BACKEND PYTHON — src/                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  CLIPPER API (src/gui/api.py) — Bridge exposto ao JS via pywebview      │ │
│  │  • get_video_info(url)          • start_pipeline(options)               │ │
│  │  • cancel_pipeline()            • get_status()                          │ │
│  │  • get_projects()               • get_project_clips(slug)               │ │
│  │  • update_clip_details()        • open_folder() / open_video()          │ │
│  │  • get_system_info()            • save_gemini_api_key()                 │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                      │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  PIPELINE ENGINE (src/core/pipeline.py)                                 │ │
│  │  PipelineEngine + PipelineOptions + PipelineProgress                    │ │
│  │  6 etapas: metadata → heatmap → download → transcribe → heuristics →    │ │
│  │             cutting (com cancelamento via threading.Event)               │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                      │
│         ┌────────────────────────────┼────────────────────────────┐         │
│         ▼                            ▼                            ▼         │
│  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐    │
│  │  SERVICES   │            │  HEURISTICS │            │   UTILS     │    │
│  │  gemini_    │            │  8 scores   │            │  cut_clip,  │    │
│  │  service    │            │  + heatmap  │            │  cut_long,  │    │
│  │  youtube_   │            │  orchestrator│           │  transcribe,│    │
│  │  service    │            │  (apply_    │            │  face_detect│    │
│  │             │            │  heuristics)│            │  subtitles  │    │
│  └─────────────┘            └─────────────┘            └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SERVIDOR HTTP LOCAL (Bottle) — src/gui/server.py                           │
│  • Porta 48123 (auto-detect)                                                │
│  • Serve static: / → client/dist/index.html                                 │
│  • Serve media:  /media/<slug>/clips/*.mp4  (com Accept-Ranges para scrub)  │
│  • CORS habilitado para dev                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  RECURSOS EXTERNOS                                                          │
│  • YouTube (yt-dlp): metadados, legendas, heatmap, download                │
│  • Google Gemini API: seleção semântica + metadados                         │
│  • FFmpeg (sistema): jump cut, encode, concat                               │
│  • MediaPipe (models/blaze_face_short_range.tflite): face detection         │
│  • Faster-Whisper (CTranslate2): transcrição local                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Componentes Principais

### 2.1 PyWebView Desktop Bridge

| Direção | Mecanismo | Exemplos |
|---------|-----------|----------|
| **JS → Python** | `window.pywebview.api.metodo(args)` retorna `Promise` | `api.start_pipeline({...})`, `api.get_projects()` |
| **Python → JS** | `window.__clipperBridge.emit(event, payload)` via `evaluate_js` | `progress`, `log`, `clip_done`, `pipeline_finished` |

**Código do Bridge (src/gui/api.py):**
```python
def _emit_to_js(self, event_name: str, payload: Any) -> None:
    if not self._window:
        return
    payload_json = json.dumps(payload, ensure_ascii=False)
    script = f"window.__clipperBridge && window.__clipperBridge.emit({json.dumps(event_name)}, {payload_json});"
    self._window.evaluate_js(script)
```

**Eventos emitidos:**
| Evento | Payload | Descrição |
|--------|---------|-----------|
| `progress` | `{step, step_index, percentage, message, current_clip, total_clips, data}` | Atualiza stepper + barra + contador |
| `log` | `{level: "info"\|"warning"\|"error", message}` | Linha de log colorida no console |
| `clip_done` | `{name, score, video_file, video_url, ...}` | Clipe finalizado (renderizado ou timestamps) |
| `pipeline_finished` | `{success, result?, error?}` | Fim do pipeline (sucesso/erro/cancel) |

---

### 2.2 PipelineEngine (src/core/pipeline.py)

**Dataclasses centrais:**

```python
@dataclass
class PipelineOptions:
    video_url: str
    transcription_mode: str = MODE_YT_PARTIAL  # whisper | yt_full | yt_partial
    render_subtitles: bool = True
    use_whisper_subtitles: bool = True
    use_heatmap: bool = True
    output_base_dir: str = "output"
    apply_vignette: bool = True
    vignette_angle: str = "PI/4"          # PI/4 | PI/5 | PI/3.5
    enable_split_screen: bool = True
    split_screen_chance: float = 0.5
    only_timestamps: bool = False
    clipping_strategy: str = STRATEGY_AI   # ai | heuristics
    gemini_model: str = "gemini-2.5-flash"
    # Long clips (16:9)
    is_long_clip: bool = False
    remove_silence: bool = True
    silence_threshold_db: float = -30.0
    min_silence_duration: float = 0.6
    silence_padding: float = 0.15
    min_clip_duration: float = 180.0
    max_clip_duration: float = 1200.0
    max_clips: int = 3
    custom_start_time: float | None = None
    custom_end_time: float | None = None
    delete_original_video: bool = True
    long_clip_overlay: str | None = None

@dataclass
class PipelineProgress:
    step: str                    # init, metadata, heatmap, download, transcribe,
                                 # heuristics, clips_plan, cutting, done, error, cancelled
    step_index: int              # 1..6
    total_steps: int = 6
    percentage: float = 0.0
    message: str = ""
    current_clip: int = 0
    total_clips: int = 0
    data: dict = field(default_factory=dict)
```

**Execução assíncrona com cancelamento:**

```python
# Em ClipperApi.start_pipeline():
self._cancel_token = threading.Event()
self._pipeline_thread = threading.Thread(target=worker, daemon=True)
self._pipeline_thread.start()

# Em PipelineEngine.run():
def _check_cancelled(self) -> bool:
    if self.cancel_token and self.cancel_token.is_set():
        # emite progress cancelled, log warning
        return True
    return False
```

---

### 2.3 Domínio: Segment

```python
# src/domain/segment.py
from dataclasses import dataclass

@dataclass
class Segment:
    start: float          # início em segundos
    end: float            # fim em segundos
    text: str             # texto original
    norm: str             # lowercase, sem pontuação (para matching regex)
    score: float = 0.0    # acumulado pelas heurísticas
```

---

### 2.4 Servidor Bottle Local (src/gui/server.py)

```python
@app.route("/media/<filepath:path>")
def serve_media(filepath):
    """Serve video files with automatic Accept-Ranges support for scrubbing."""
    return static_file(filepath, root=output_dir, mimetype="video/mp4")
```

- **Porta:** 48123 (auto-detecta livre com `find_free_port`)
- **CORS:** Habilitado (`*`)
- **Range Requests:** Suportados nativamente pelo `static_file` do Bottle → permite *seeking* instantâneo no `<video>` HTML

---

## 3. Fluxo de Dados Completo

```
INPUT (YouTube URL)
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. METADADOS (PipelineEngine.get_video_info via yt-dlp)      │
│    → title, thumbnail, duration, uploader, view_count, desc  │
│    → slug = slugify(title)                                    │
│    → output_dir = output/<slug>/, clips_dir = output/<slug>/clips/
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. HEATMAP (opcional) — get_youtube_heatmap(video_url)       │
│    → Lista de janelas: [{start, end, intensity: 0.0-1.0}]    │
│    → Usa yt-dlp `heatmap` extractor                           │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. PREPARAÇÃO / DOWNLOAD                                     │
│    Se only_timestamps: pula download                         │
│    Se whisper ou yt_full: baixa vídeo completo 720p (bestv)  │
│    Se yt_partial: adia download para etapa de corte          │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. TRANSCRIÇÃO                                               │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ MODE_WHISPER:    video → MP3 → faster-whisper        │  │
│    │ MODE_YT_FULL:    video completo → legendas YT        │  │
│    │ MODE_YT_PARTIAL: legendas YT (sem download vídeo)    │  │
│    │ Fallback automático: YT falhou → Whisper local       │  │
│    └──────────────────────────────────────────────────────┘  │
│    → segments.json (lista de Segment)                        │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. SELEÇÃO DE CORTES (IA OU HEURÍSTICAS)                     │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ STRATEGY_AI (Gemini):                                │  │
│    │   → ai_create_clips / ai_create_long_clips           │  │
│    │   → Prompt estruturado + JSON Schema                 │  │
│    │   → Retorna lista de clips (lista de Segment) + meta │  │
│    │   → Fallback: se erro ou sem key → heurísticas       │  │
│    └──────────────────────────────────────────────────────┘  │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ STRATEGY_HEURISTICS:                                 │  │
│    │   → apply_heuristics(segment, all_segments, heatmap) │  │
│    │   → 8 scores mutam segment.score in-place            │  │
│    │   → create_clips(segments, max_clips) agrupa         │  │
│    └──────────────────────────────────────────────────────┘  │
│    → clips.json (plano de cortes)                            │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 6. RENDERIZAÇÃO (ou apenas timestamps)                       │
│    Para cada clipe:                                          │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ only_timestamps:                                     │  │
│    │   → salva timestamps.json + timestamps.txt           │  │
│    │   → gera metadados via Gemini (generate_video_details)│  │
│    └──────────────────────────────────────────────────────┘  │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ is_long_clip (16:9):                                 │  │
│    │   → cut_horizontal_clip_with_silence_removal()       │  │
│    │   → FFmpeg silencedetect + concat + overlay opcional │  │
│    └──────────────────────────────────────────────────────┘  │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ Shorts 9:16:                                         │  │
│    │   → cut_clip()                                       │  │
│    │   → sample_frames_fast() → detect_faces() (MediaPipe)│  │
│    │   → smooth_positions() → crop vertical face-tracking │  │
│    │   → split_screen (2 faces) chance configurável       │  │
│    │   → legendas ASS pop-in (generate_subtitles)         │  │
│    │   → vignette (PI/4, PI/5, PI/3.5)                    │  │
│    │   → música de fundo aleatória (assets/audios/musics/) │  │
│    └──────────────────────────────────────────────────────┘  │
│    → clip_XX.mp4 + clip_XX_details.json                      │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
OUTPUT
├── output/<slug>/
│   ├── segments.json
│   ├── clips.json
│   ├── timestamps.json
│   ├── timestamps.txt
│   └── clips/
│       ├── clip_00.mp4
│       ├── clip_00_details.json
│       └── ...
```

---

## 4. Estrutura de Módulos Python (src/)

```
src/
├── main.py                          # CLI interativo (questionary)
├── core/
│   └── pipeline.py                  # PipelineEngine, PipelineOptions, PipelineProgress
├── domain/
│   └── segment.py                   # Dataclass Segment
├── heuristics/
│   ├── __init__.py                  # exporta apply_heuristics
│   ├── appy_heuristics.py           # orquestrador (typo intencional)
│   ├── score_contrast.py            # +0.7: "antes/agora", "todo mundo/mas"
│   ├── score_cta.py                 # -100: CTAs de final de vídeo
│   ├── score_heatmap.py             # +3.0 × intensidade média
│   ├── score_length.py              # +0.3: 8-20 palavras
│   ├── score_pause.py               # +0.2: pausa > 0.4s antes
│   ├── score_personal.py            # +0.5: "eu", "meu", "achei", "senti"
│   ├── score_question.py            # +0.4: termina com "?"
│   ├── score_time.py                # -100: primeiro minuto ou timestamp duplicado
│   └── score_triggers.py            # +1.0: "presta atenção", "segredo", etc.
├── services/
│   ├── __init__.py                  # exporta generate_video_details, get_gemini_api_key
│   ├── gemini_service.py            # IA: seleção + metadados (prompts, schemas, fallbacks)
│   └── youtube_service.py           # Upload YouTube (opcional)
├── utils/
│   ├── __init__.py                  # facade: re-exporta tudo
│   ├── ai_create_clips.py           # Gemini: seleção Shorts (prompts complexos)
│   ├── ai_create_long_clips.py      # Gemini: seleção Long Clips (temas 3-20min)
│   ├── create_clips.py              # Agrupamento heurístico → lista de clips
│   ├── cut_clip.py                  # Shorts 9:16: face tracking, split, subs, vignette
│   ├── cut_long_clip.py             # Long 16:9: FFmpeg silence removal + overlay
│   ├── detect_face_center.py        # MediaPipe blaze_face_short_range.tflite
│   ├── download_clip_segment.py     # yt-dlp range download (parcial)
│   ├── generate_subtitles.py        # ASS pop-in animado
│   ├── get_youtube_heatmap.py       # yt-dlp heatmap extractor
│   ├── get_youtube_transcription.py # yt-dlp legendas + fallback
│   ├── normalize_text.py            # lowercase, remove pontuação
│   ├── slugify.py                   # URL-safe slug
│   ├── transcribe_audio.py          # faster-whisper wrapper
│   ├── transcribe_clip.py           # Whisper só no trecho do clipe
│   └── video_to_mp3.py              # MoviePy audio extraction
└── gui/
    ├── __init__.py
    ├── api.py                       # ClipperApi (bridge pywebview)
    ├── server.py                    # Bottle HTTP server (static + media)
    ├── app.py                       # Entry point: cria window + server + api
    └── web/                         # Frontend build (client/dist) servido aqui
```

---

## 5. Frontend React (client/)

```
client/
├── src/
│   ├── main.tsx                     # React 19 + createRoot
│   ├── App.tsx                      # Layout: Header + Tabs + Toast (Sonner)
│   ├── components/
│   │   ├── header.tsx               # Logo, tabs, system status pill
│   │   ├── sidebar.tsx              # Navegação lateral (mobile)
│   │   ├── pipeline-monitor.tsx     # Stepper 6 passos + progress + console logs
│   │   ├── shorts-studio-tab.tsx    # Aba Shorts: URL, strategy, mode, options
│   │   ├── long-clips-tab.tsx       # Aba Long Clips: URL, AI/custom, silence params
│   │   ├── library-tab.tsx          # Projetos dropdown + grid de clips
│   │   ├── video-preview-card.tsx   # Player + metadados editáveis + actions
│   │   └── diagnostic-tab.tsx       # API keys, face model, paths, tips
│   ├── hooks/
│   │   ├── use-clipper-status.ts    # Polling get_status + event listeners
│   │   └── use-mobile.ts            # Breakpoint detector
│   ├── lib/
│   │   ├── bridge.ts                # Tipos TS para window.pywebview.api + events
│   │   └── utils.ts                 # cn(), formatTime(), etc.
│   └── types/
│       └── api.ts                   # PipelineOptions, ClipItem, ProgressData, etc.
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts (v4 via @tailwindcss/vite)
└── components.json                  # Shadcn/ui config
```

---

## 6. Dependências Críticas

| Pacote | Versão | Uso |
|--------|--------|-----|
| `python` | 3.12 | Runtime |
| `poetry` | - | Gerenciador de deps |
| `yt-dlp` | 2026.8.19 | YouTube: info, download, heatmap, legendas |
| `faster-whisper` | 1.0.3 | Transcrição local (CTranslate2) |
| `mediapipe` | 0.10.32 | Face detection (blaze_face_short_range.tflite) |
| `opencv-python` | 4.13 | Video capture, frame sampling |
| `moviepy` | 2.2.1 | Video/audio processing, compositing |
| `ffmpeg-python` | 0.2.0 | Wrapper FFmpeg (usado via subprocess direto) |
| `pydantic` | 2.10 | Validação de schemas (Gemini structured output) |
| `ai` | 0.8.0 | Vercel AI SDK (Gemini client) |
| `pywebview` | 6.2.1 | Desktop window |
| `bottle` | - | HTTP server local |
| `questionary` | 2.1.1 | CLI interativo |
| `tqdm` | 4.67.2 | Progress bars CLI |

**Frontend:**
| Pacote | Versão | Uso |
|--------|--------|-----|
| `react` | 19.2.8 | UI |
| `typescript` | 6.0.2 | Tipagem |
| `vite` | 8.3.0 | Build + dev server |
| `tailwindcss` | 4.3.3 | Styling (v4 via Vite plugin) |
| `shadcn` | 4.22.0 | Componentes base Radix |
| `@base-ui/react` | 1.9.0 | Primitivas acessíveis |
| `@phosphor-icons/react` | 2.1.10 | Ícones |
| `sonner` | 2.0.8 | Toasts |
| `next-themes` | 0.4.6 | Dark mode |
| `class-variance-authority` | 0.7.1 | Variantes de componentes |

---

## 7. Modelos e Assets Locais

```
models/
└── blaze_face_short_range.tflite     # MediaPipe face detection (obrigatório)

assets/
├── overlays/
│   └── frame.png                     # Overlay 16:9 padrão (opcional, via DEFAULT_LONG_CLIP_OVERLAY)
└── audios/
    └── musics/
        ├── track1.mp3                # Músicas de fundo para Shorts (seleção aleatória)
        └── ...
```

---

## 8. Variáveis de Ambiente (.env)

```env
# Obrigatório
GEMINI_API_KEY="..."                  # Google AI Studio
GEMINI_MODEL="gemini-2.5-flash"       # Modelo principal
GEMINI_FALLBACK_MODELS="gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash"

# Opcionais
VITE_DEV_URL="http://localhost:5173"  # HMR no PyWebView (dev)
AUTOCLIP_DEBUG="false"                # DevTools no PyWebView
DEFAULT_LONG_CLIP_OVERLAY="assets/overlays/frame.png"
# AI_GATEWAY_API_KEY=""               # Vercel AI Gateway (se usar)
```

---

## 9. Execução

```bash
# GUI Desktop (recomendado)
poetry run gui
# ou
poetry run python -m src.gui.app

# CLI Interativo
poetry run start
# ou
poetry run python src/main.py

# Frontend Dev (HMR) — Terminal separado
cd client && npm run dev
# Configure VITE_DEV_URL=http://localhost:5173 no .env
```

---

## 10. Próximos Passos na Documentação

- [PIPELINE.md](PIPELINE.md) — Detalhamento de cada etapa, fallbacks, cancelamento
- [HEURISTICS.md](HEURISTICS.md) — Fórmulas, pesos, anti-heurísticas, heatmap
- [GEMINI_SERVICE.md](GEMINI_SERVICE.md) — Prompts, schemas JSON, retry/fallback
- [VIDEO_PROCESSING.md](VIDEO_PROCESSING.md) — Face tracking, split-screen, ASS, jump cut
- [FRONTEND.md](FRONTEND.md) — Componentes, hooks, bridge types, Shadcn/ui
- [CONFIG_AND_ENV.md](CONFIG_AND_ENV.md) — Config completa, requisitos, saída