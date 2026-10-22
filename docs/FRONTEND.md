# Frontend React — Interface de Usuário

Este documento especifica a arquitetura, estrutura de componentes, estado reativo e integração com o backend Python do frontend do **AutoClip Studio** (`client/`).

---

## 1. Visão Geral da Stack

- **Framework:** React 19 + TypeScript 6
- **Build Tool:** Vite 8 (com suporte a DevServer HMR na porta 5173 e build de produção estático para `src/gui/web/`)
- **Estilização:** Tailwind CSS v4 (via `@tailwindcss/vite` plugin)
- **Design System & Componentes:** Radix UI / Base UI, Phosphor Icons (`@phosphor-icons/react`), Sonner Toasts
- **Injeção Desktop:** `window.pywebview.api` (promessas assíncronas) + `window.__clipperBridge` (barramento de eventos)

---

## 2. Estrutura de Diretórios (`client/src/`)

```
client/src/
├── main.tsx                     # Entry point React 19 createRoot
├── App.tsx                      # Layout mestre: Sidebar + Header + Main Area + Toaster
├── components/
│   ├── header.tsx               # Barra superior com estatísticas, modelo ativo e badge de status
│   ├── sidebar.tsx              # Menu lateral com ícones e navegação entre abas
│   ├── pipeline-monitor.tsx     # Stepper de 6 fases, barra de progresso e console de logs
│   ├── shorts-studio-tab.tsx    # Aba 1: Estúdio de Shorts Verticais (9:16)
│   ├── long-clips-tab.tsx       # Aba 2: Estúdio de Cortes Longos Horizontais (16:9)
│   ├── library-tab.tsx          # Aba 3: Biblioteca de Projetos (Galeria e metadados)
│   ├── video-preview-card.tsx   # Card de clipe: Player HTML5 + editor de título/descrição/tags
│   ├── diagnostic-tab.tsx       # Aba 4: Configurações, chave Gemini, modelo e caminhos
│   └── ui/                      # Componentes base Shadcn (Button, Card, Input, Slider, Switch, Badge, Tabs, etc.)
├── hooks/
│   ├── use-clipper-status.ts    # Hook customizado de estado, polling e escuta de eventos
│   └── use-mobile.ts            # Hook responsivo para detecção de viewport
├── lib/
│   ├── bridge.ts                # Inicialização e subscrição de eventos PyWebView
│   └── utils.ts                 # Utilitários de classe `cn()` e formatação
└── types/
    └── api.ts                   # Interfaces estritas para todas as entidades e métodos da Bridge
```

---

## 3. Integração e Comunicação com o Python (`bridge.ts`)

### 3.1 Padrão de Injeção PyWebView (`getClipperApi`)
O PyWebView injeta o objeto `window.pywebview.api` assincronamente ao inicializar a janela nativa. A função `getClipperApi()` escuta o evento `pywebviewready` ou resolve via Promise com fallback de segurança:

```typescript
export async function getClipperApi(): Promise<ClipperApi> {
    if (typeof window !== "undefined" && window.pywebview?.api) {
        return window.pywebview.api
    }
    return new Promise((resolve) => {
        const handler = () => {
            window.removeEventListener("pywebviewready", handler)
            if (window.pywebview?.api) resolve(window.pywebview.api)
        }
        window.addEventListener("pywebviewready", handler)
        setTimeout(() => {
            if (window.pywebview?.api) resolve(window.pywebview.api)
        }, 2000)
    })
}
```

### 3.2 Subscrição de Eventos em Tempo Real (`subscribeToClipperEvents`)
Cria a ponte `window.__clipperBridge` para registrar callbacks para os 4 eventos transmitidos pelo Python:

```typescript
subscribeToClipperEvents({
    onProgress: (progressData) => { /* atualiza stepper e progresso */ },
    onLog: (logItem) => { /* adiciona linha no console */ },
    onClipDone: (clipData) => { /* exibe toast "Corte finalizado" */ },
    onPipelineFinished: (result) => { /* finaliza execução */ }
})
```

---

## 4. Hook de Estado do Pipeline (`useClipperStatus.ts`)

Centraliza a lógica de execução e sincronização com o backend:

```typescript
const {
    isRunning,        // boolean: indica se há um pipeline ativo
    progress,         // ProgressData: passo atual, porcentagem, mensagem, clipe X de Y
    logs,             // LogItem[]: linhas de log registradas (máximo 500)
    startPipeline,    // (options: PipelineOptions) => Promise<boolean>
    cancelPipeline,   // () => Promise<boolean>
    clearLogs,        // () => void
    refreshStatus     // () => Promise<void>
} = useClipperStatus()
```

### Polling de Segurança
Além de receber eventos push em tempo real, o hook executa polling a cada `1500ms` enquanto `isRunning === true` chammando `api.get_status()` para garantir que a UI se recupere caso a janela perca eventos durante interrupções.

---

## 5. Abas da Aplicação e Suas Responsabilidades

### 5.1 Estúdio de Shorts Verticais (`shorts-studio-tab.tsx`)
- **Input de URL:** Aceita links do YouTube (`youtube.com` ou `youtu.be`). Botão para colar da área de transferência.
- **Preview do Vídeo:** Exibe card com thumbnail, título, autor, duração e visualizações via `api.get_video_info(url)`.
- **Estratégia de Seleção:** Radio button entre IA Gemini (recomendado) ou Heurísticas + Heatmap.
- **Modo de Download:** Select entre Legendas YouTube Parcial, Legendas YouTube Completo ou Whisper Local.
- **Toggles e Opções Virais:**
  - Impulso com Heatmap do YouTube
  - Renderizar legendas animadas no vídeo
  - Re-transcrever legendas com Whisper para precisão
  - Split-screen dinâmico (2 pessoas) + probabilidade
  - Efeito vinheta + intensidade
  - Apenas Timestamps (sem renderização)
  - Quantidade máxima de cortes (1 a 15)

---

### 5.2 Estúdio de Cortes Longos 16:9 (`long-clips-tab.tsx`)
- **Seleção do Tema:** IA Gemini (tópicos fechados de 3 a 20 min) ou Intervalo Personalizado (`custom_start_time` / `custom_end_time`).
- **Sliders de Duração e Quantidade:** Duração mínima (2-15 min), máxima (5-20 min) e quantidade de cortes (1-5).
- **Remoção de Silêncios (Jump Cut FFmpeg):**
  - Toggle de ativação.
  - Presets de sensibilidade: Suave (-35dB), Padrão (-30dB), Agressivo (-25dB).
  - Configuração avançada de threshold (dB), duração da pausa e margem de segurança (*padding*).
- **Overlay 16:9:** Permite selecionar um arquivo de imagem (PNG/JPG) local com botão nativo e salvar como padrão no `.env`.

---

### 5.3 Biblioteca de Projetos (`library-tab.tsx`)
- **Seletor de Projetos:** Dropdown alimentado por `api.get_projects()` ordenado pelos projetos mais recentes em `output/`.
- **Informações do Projeto:** Mostra contagem de cortes, data de modificação e badge indicativo (`🎬 Vídeos Renderizados` ou `⏱️ Apenas Timestamps`).
- **Ações Globais:** Botão "Abrir Pasta do Projeto" (chama `api.open_folder(path)`).
- **Grid de Cards:** Renderiza os cortes com o componente `video-preview-card.tsx`.

---

### 5.4 Card de Preview do Clipe (`video-preview-card.tsx`)
- **Player HTML5:** Tag `<video>` com suporte a streaming via `/media/<slug>/clips/clip_XX.mp4`.
- **Edição de Metadados:**
  - Título editável (`Input`)
  - Descrição editável (`Textarea`)
  - Tags/Hashtags em pílulas (`Badge`)
- **Ações:**
  - **Salvar:** Grava as alterações no arquivo `_details.json` via `api.update_clip_details(...)`.
  - **Copiar:** Copia o título, descrição formatada e hashtags prontas para publicação para o Clipboard com toast informativo.
  - **Player Externo:** Abre o arquivo `.mp4` no player nativo do sistema (ex: VLC) via `api.open_video(path)`.

---

### 5.5 Painel de Diagnóstico & Configurações (`diagnostic-tab.tsx`)
- **Status do Gemini:** Indica se a chave `GEMINI_API_KEY` está configurada, mostra preview seguro (`AIza...1234`), permite digitar nova chave e salvá-la direto no `.env` via `api.save_gemini_api_key()`.
- **Modelo Gemini:** Select para trocar o modelo ativo (`gemini-3.8-flash`, `gemini-flash-latest`, `gemini-3.5-flash-lite`) salvando via `api.save_gemini_model()`.
- **Overlay Padrão:** Exibe o caminho do arquivo de overlay 16:9 ativo com seletor de arquivo nativo.
- **Status do Modelo Facial:** Checa se o arquivo `models/blaze_face_short_range.tflite` existe.
- **Ambiente:** Versão do Python e caminho absoluto do workspace e da pasta `output/`.

---

## 6. Monitor de Execução (`pipeline-monitor.tsx`)

Renderiza em tempo real durante o processamento:

1. **Stepper de Fases (6 Etapas):**
   - Metadados → Heatmap → Preparação → Transcrição → Seleção IA/Heurística → Renderização
   - Ícones com estado ativo (spinner animado), concluído (check verde) ou pendente.
2. **Barra de Progresso:** Progresso de $0\%$ a $100\%$ com indicador de clipe atual ($X$ de $Y$).
3. **Console de Logs (Terminal):**
   - Visualizador estilo terminal escuro com rolagem automática.
   - Destaque de cor por nível de log: `INFO` (cinza/azul), `WARNING` (amarelo), `ERROR` (vermelho).
   - Botão para limpar logs do console.
4. **Botão de Cancelamento:** Dispara `api.cancel_pipeline()`.

---

## 7. Scripts de Build e Desenvolvimento

No diretório `client/`:

```bash
npm run dev        # Inicia servidor Vite na porta 5173 (com HMR)
npm run build      # Executa tsc -b e compila bundles otimizados para client/dist/
npm run lint       # Roda ESLint + Oxlint
npm run format     # Formata código com Prettier
```

Para conectar a janela do PyWebView ao servidor de desenvolvimento Vite durante a criação de recursos frontend, configure no arquivo `.env` do projeto principal:
```env
VITE_DEV_URL="http://localhost:5173"
```
Isso faz o PyWebView carregar a URL do Vite com Hot Module Replacement em vez do arquivo estático compilado.
