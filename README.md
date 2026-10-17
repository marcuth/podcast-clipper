# Podcast Clipper

Extrai clipes curtos de podcasts no YouTube com transcrição, cortes inteligentes baseados em heuristicas, legendas e metadados gerados por LLM.

## Funcionalidades

- **Download automático** de vídeos do YouTube via yt-dlp
- **Transcrição** por Whisper (local) ou legendas do YouTube
- **Pontuação de segmentos** por heurísticas (contraste, perguntas, CTA, pausas, heatmap do YouTube, etc.)
- **Corte com tracking facial** usando MediaPipe (formato 9:16 para Shorts/Reels)
- **Legendas embutidas** no vídeo (com suporte a re-transcrição por Whisper)
- **Metadados automáticos** (título, descrição, tags) via Groq LLM
- **Download parcial** — baixa apenas os segmentos necessários, sem o vídeo inteiro
- **Música de fundo** opcional

## Requisitos

- Python 3.11
- [Poetry](https://python-poetry.org/)
- FFmpeg (instalado no sistema e disponível no PATH)

## Instalação

```bash
poetry install
```

Copie `.env.example` para `.env` e configure sua chave da Groq (necessário apenas para geração de metadados):

```env
GROQ_API_KEY=sua_chave_aqui
```

## Uso

```bash
poetry run start
```

O pipeline interativo vai guiar você por:
1. URL do vídeo do YouTube
2. Modo de transcrição (Whisper local / legendas do YouTube)
3. Geração de clipes com heurísticas
4. Corte, legendas e metadados

## Estrutura

```
src/
├── main.py              # entry point
├── domain/              # modelos (Segment)
├── heuristics/          # pontuação de segmentos
├── services/            # Groq LLM, YouTube API
└── utils/               # utilidades (download, corte, legendas, etc.)
```

A saída dos clipes fica em `output/<slug-do-video>/clips/`.

## Licença

MIT
