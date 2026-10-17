# Index da Documentação Técnica — AutoClip Studio

Bem-vindo à documentação técnica do **AutoClip Studio** (Podcast Clipper). Esta pasta reúne guias detalhados de arquitetura, motores de IA e estatística, processamento de mídia e integração do frontend.

---

## 📚 Estrutura da Documentação

| Documento | Descrição |
|-----------|-----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Visão geral da arquitetura, backend Python, frontend React, servidor Bottle e PyWebView Desktop Bridge |
| [PIPELINE.md](PIPELINE.md) | Detalhes do `PipelineEngine`: fluxo de 6 etapas, opções de execução, fallbacks e cancelamento |
| [HEURISTICS.md](HEURISTICS.md) | As 8 heurísticas de pontuação de texto, tempo e áudio + integração com Heatmap do YouTube |
| [GEMINI_SERVICE.md](GEMINI_SERVICE.md) | Seleção de cortes e metadados via Google Gemini API: prompts, esquemas de saída e resiliência de modelos |
| [VIDEO_PROCESSING.md](VIDEO_PROCESSING.md) | Engenharia de vídeo: MediaPipe face tracking, split-screen, legendas ASS pop-in, jump cut FFmpeg, vignette e overlay |
| [FRONTEND.md](FRONTEND.md) | Estrutura da UI em React + TypeScript + Vite + Tailwind v4 + Shadcn/ui: abas, hooks e tipagem da Bridge |
| [CONFIG_AND_ENV.md](CONFIG_AND_ENV.md) | Configuração de ambiente (`.env`), requisitos de sistema (FFmpeg/MediaPipe), scripts e estrutura de saída |
| [CLI.md](CLI.md) | Referência do CLI interativo (questionary) |
| [CONCEITOS_INTERFACE.md](CONCEITOS_INTERFACE.md) | Especificação detalhada dos componentes visuais, fluxos de uso e campos das abas |
| [heuristicas_simples_para_pegar_momentos_de_destaque.md](heuristicas_simples_para_pegar_momentos_de_destaque.md) | Conceitos teóricos sobre regras de viralidade em áudio e texto para conversas |

---

## 🛠️ Tecnologias Principais

- **Backend:** Python 3.12, Poetry, `yt-dlp`, `faster-whisper`, `MediaPipe`, `MoviePy`, `OpenCV`, `FFmpeg`
- **Desktop & Server:** `pywebview` 6.x (janela nativa Windows), `Bottle` (streaming de vídeo via Range Requests)
- **Frontend:** React 19, TypeScript, Vite 8, Tailwind CSS v4, Radix / Shadcn UI, Phosphor Icons
- **IA LLM:** Google Gemini API (`gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`)
