# AutoClip Studio — Client Frontend (React + TypeScript + Vite)

Este é o frontend da aplicação desktop **AutoClip Studio**, desenvolvido em **React 19 + TypeScript + Vite + Tailwind CSS v4 + Shadcn/ui**.

A interface é executada e renderizada dentro da janela desktop nativa via **PyWebView** (`src/gui/app.py`), comunicando-se com o backend Python em tempo real através do objeto injetado `window.pywebview.api` e do barramento de eventos `window.__clipperBridge`.

---

## 🚀 Tecnologias e Bibliotecas

- **UI & Framework:** React 19, TypeScript 6, Vite 8
- **Estilização:** Tailwind CSS v4 (`@tailwindcss/vite`), Radix / Base UI (`@base-ui/react`), `class-variance-authority`, `tw-animate-css`
- **Ícones & Notificações:** Phosphor Icons (`@phosphor-icons/react`), Sonner (`sonner` toasts)
- **Code Quality:** ESLint 10, Oxlint, Prettier

---

## 📂 Estrutura de Diretórios (`src/`)

```
src/
├── main.tsx                   # Ponto de entrada do React
├── App.tsx                    # Layout mestre (Sidebar, Header, Main Content e Toaster)
├── components/
│   ├── header.tsx             # Cabeçalho com título da página e status do pipeline
│   ├── sidebar.tsx            # Navegação lateral entre abas
│   ├── pipeline-monitor.tsx   # Stepper visual das 6 fases + barra + console de logs
│   ├── shorts-studio-tab.tsx  # Aba 1: Estúdio de Shorts Verticais (9:16)
│   ├── long-clips-tab.tsx     # Aba 2: Estúdio de Cortes Longos (16:9)
│   ├── library-tab.tsx        # Aba 3: Biblioteca de Projetos (Galeria)
│   ├── video-preview-card.tsx # Player de vídeo HTML5 + edição de metadados
│   ├── diagnostic-tab.tsx     # Aba 4: Configurações de API Keys, modelos e ambiente
│   └── ui/                    # Componentes Shadcn (Button, Card, Input, Slider, Switch, Badge, etc.)
├── hooks/
│   ├── use-clipper-status.ts  # Hook de estado do pipeline (polling + eventos bridge)
│   └── use-mobile.ts          # Detecção de tamanho de tela
├── lib/
│   ├── bridge.ts              # Funções helper para conectar na API do PyWebView
│   └── utils.ts               # Utilitários de classe `cn()` e formatadores
└── types/
    └── api.ts                 # Interfaces TypeScript do PyWebView e dos modelos de dados
```

---

## 🛠️ Comandos de Desenvolvimento

No diretório `client/`:

```bash
# Iniciar servidor de desenvolvimento do Vite (HMR na porta 5173)
npm run dev

# Compilar arquivos para produção (gera bundles otimizados em client/dist)
npm run build

# Executar verificação de linter
npm run lint

# Formatar o código com Prettier
npm run format
```

---

## 🔗 Integração com o PyWebView em Desenvolvimento (HMR)

Para testar alterações na interface com carregamento instantâneo (Hot Module Replacement) dentro da janela nativa desktop:

1. No terminal 1 (pasta `client/`):
    ```bash
    npm run dev
    ```
2. No arquivo `.env` na raiz do projeto principal, defina:
    ```env
    VITE_DEV_URL="http://localhost:5173"
    ```
3. No terminal 2 (raiz do projeto):
    ```bash
    poetry run gui
    ```

A janela do PyWebView carregará a URL do Vite DevServer mantendo a ponte Python/JS totalmente funcional.
