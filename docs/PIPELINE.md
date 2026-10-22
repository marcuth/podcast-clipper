# PipelineEngine e Fluxo de Processamento

Este documento detalha o funcionamento interno do **`PipelineEngine`** (`src/core/pipeline.py`), o motor responsável por orquestrar todas as etapas do corte automatizado de vídeos.

---

## 1. Visão Geral do PipelineEngine

O `PipelineEngine` executa o fluxo sequencial de 6 etapas e suporta:
- **Relatório de Progresso em Tempo Real:** Comunicação por callbacks (`on_progress`, `on_log`, `on_clip_done`).
- **Cancelamento Assíncrono:** Utilização de `threading.Event` (`cancel_token`) verificado antes de cada sub-tarefa custosa.
- **Fallbacks Automáticos:** Troca de estratégias em runtime quando um recurso falha (ex: legendas do YouTube indísponíveis → Whisper local; chave de IA zerada → heurísticas estatísticas).

```python
engine = PipelineEngine(
    on_progress=my_progress_callback,
    on_log=my_log_callback,
    on_clip_done=my_clip_done_callback,
    cancel_token=my_cancel_token
)
result = engine.run(options)
```

---

## 2. Opções do Pipeline (`PipelineOptions`)

A classe `@dataclass PipelineOptions` configura o comportamento completo da execução:

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `video_url` | `str` | *obrigatório* | URL do vídeo do YouTube (validada via regex) |
| `transcription_mode` | `str` | `"yt_full"` | `whisper` \| `yt_full` \| `yt_partial` |
| `clipping_strategy` | `str` | `"ai"` | `"ai"` (Gemini) \| `"heuristics"` (Estatística) |
| `gemini_model` | `str` | `"gemini-3.8-flash"` | Modelo principal para análises do Gemini |
| `only_timestamps` | `bool` | `False` | Se `True`, não baixa nem renderiza vídeos (apenas gera horários e metadados) |
| `is_long_clip` | `bool` | `False` | Se `True`, ativa o modo de cortes horizontais (16:9) |
| `max_clips` | `int` | `8` (Shorts) / `3` (Long) | Quantidade máxima de cortes extraídos |
| `render_subtitles` | `bool` | `True` | Grava legendas dinâmicas no vídeo (Shorts) |
| `use_whisper_subtitles` | `bool` | `True` | Re-transcreve o clipe final com Whisper local para legendas milimétricas |
| `use_heatmap` | `bool` | `True` | Consulta curva "mais reproduzido" do YouTube |
| `apply_vignette` | `bool` | `True` | Aplica efeito vinheta escurecendo bordas (Shorts) |
| `vignette_angle` | `str` | `"PI/4"` | Intensidade da vinheta: `"PI/5"` (suave), `"PI/4"` (moderada), `"PI/3.5"` (intensa) |
| `enable_split_screen` | `bool` | `True` | Habilita tela dividida para 2 pessoas (Shorts) |
| `split_screen_chance` | `float` | `0.5` | Probabilidade (0.0 a 1.0) de aplicar split ao detectar 2 rostos |
| `remove_silence` | `bool` | `True` | Remove silêncios por FFmpeg (Long Clips 16:9) |
| `silence_threshold_db` | `float` | `-30.0` | Limite de ruído em dB para detecção de silêncio |
| `min_silence_duration` | `float` | `0.6` | Duração mínima em segundos da pausa a ser cortada |
| `silence_padding` | `float` | `0.15` | Margem de segurança em segundos mantida antes e depois da fala |
| `min_clip_duration` | `float` | `180.0` | Duração mínima para cortes longos (segundos) |
| `max_clip_duration` | `float` | `1200.0` | Duração máxima para cortes longos (segundos) |
| `custom_start_time` | `float\|None` | `None` | Início manual para corte longo em segundos |
| `custom_end_time` | `float\|None` | `None` | Fim manual para corte longo em segundos |
| `long_clip_overlay` | `str\|None` | `None` | Caminho de arquivo de imagem de overlay 16:9 |
| `delete_original_video` | `bool` | `True` | Apaga o vídeo completo temporário no fim do processo |

---

## 3. As 6 Etapas do Pipeline

```
[Etapa 1: Metadata] ──► [Etapa 2: Heatmap] ──► [Etapa 3: Download/Prep]
                                                        │
                                                        ▼
[Etapa 6: Render / Output] ◄── [Etapa 5: Seleção] ◄── [Etapa 4: Transcrição]
```

### Etapa 1: Metadados do Vídeo (5%)
- Valida a URL com regex (`youtube.com/watch?v=...` ou `youtu.be/...`).
- Chama `PipelineEngine.get_video_info(url)` que utiliza `yt-dlp` em modo `skip_download: True`.
- Extrai: `id`, `title`, `thumbnail`, `duration`, `uploader`, `view_count`, `description`.
- Cria a estrutura de pastas:
  - `output/<slug>/`
  - `output/<slug>/clips/`

### Etapa 2: Heatmap do YouTube (15%)
- Executado apenas se `use_heatmap=True`.
- Chama `get_youtube_heatmap(video_url)` para buscar os dados de retenção pública da audiência ("mais reproduzido").
- Retorna lista de janelas: `[{start, end, intensity}]` com `intensity` entre 0.0 e 1.0.
- Se o vídeo não possui heatmap ou ocorre erro, prossegue com lista vazia sem interromper o fluxo.

### Etapa 3: Preparação / Download de Vídeo (25%)
- Se `only_timestamps=True`: ignora downloads.
- Se `transcription_mode` for `whisper` ou `yt_full`: realiza download temporário do vídeo em 720p em `output/<slug>/video.mp4` via `yt-dlp`.
- Se `transcription_mode` for `yt_partial`: adiando o download para a etapa de corte para economizar banda e tempo.

### Etapa 4: Transcrição (40%)
1. **Modo `whisper`:** extrai áudio MP3 via `video_to_mp3()` e processa com `faster-whisper` (`WhisperModel("small", device="cpu", compute_type="int8")`).
2. **Modo `yt_full` ou `yt_partial`:** utiliza `get_youtube_transcription()` via `YouTubeTranscriptApi`.
   - Se as legendas falham (ex: desativadas no vídeo), o engine **automaticamente alterna para Whisper local**, baixando o áudio/vídeo completo conforme necessário.
3. Salva `output/<slug>/segments.json` formatado.

### Etapa 5: Seleção e Agrupamento dos Cortes (55%)

#### Para Cortes Longos (`is_long_clip=True`):
- Se `custom_start_time` e `custom_end_time` informados: cria clipe manual no intervalo especificado.
- Se `clipping_strategy="ai"` e `GEMINI_API_KEY` presente: chama `ai_create_long_clips()` que lê toda a transcrição e seleciona tópicos fechados de debate (3 a 20 minutos).
- Fallback: agrupa segmentos sequencialmente em blocos contínuos até atingir a duração desejada.

#### Para Shorts Verticais (9:16):
- Se `clipping_strategy="ai"` e `GEMINI_API_KEY` presente: chama `ai_create_clips()` pedindo de 20 a 85 segundos de duração por clipe.
- Se `clipping_strategy="heuristics"` ou fallback de erro na IA:
  1. Aplica as 8 heurísticas em cada segmento via `apply_heuristics()`.
  2. Agrupa segmentos com gap $\le 1.5s$ via `create_clips()`.
  3. Divide blocos longos em sub-clips de maior pontuação.
  4. Ordena por pontuação total e seleciona os Top `max_clips`.
- Salva `output/<slug>/clips.json`.

### Etapa 6: Renderização & Metadados (60% a 95%)
Para cada clipe planejado:
1. **Geração de Metadados via IA:** Chama `generate_video_details()` ou utiliza os metadados contextuais pré-calculados pelo Gemini no plano de cortes.
2. **Se `only_timestamps=True`:** apenas formata e registra as informações sem renderização.
3. **Se Shorts 9:16:**
   - Re-transcreve com Whisper se `use_whisper_subtitles=True` para obter o alinhamento de palavras.
   - Executa `cut_clip()`:
     - Amostra quadros a 4 FPS via OpenCV.
     - Detecta rostos com MediaPipe (`blaze_face_short_range.tflite`).
     - Suaviza trajetórias com filtro exponencial (exponential smoothing).
     - Se detectados 2 rostos com área $\ge 20\%$ e distância horizontal $\ge 10\%$, aplica **split-screen** conforme a probabilidade configurada.
     - Crop vertical para 9:16 (1080×1920).
     - Aplica legendas ASS com animação pop-in/bounce.
     - Aplica vinheta escura se habilitada.
     - Adiciona música de fundo aleatória se disponível em `assets/audios/musics/`.
4. **Se Corte Longo 16:9:**
   - Executa `cut_horizontal_clip_with_silence_removal()`:
     - Detecta pausas via filtro FFmpeg `silencedetect`.
     - Calcula intervalos de fala com margem de segurança (*padding*).
     - Extrai trechos falados e os concatena sem perda de sincronia de áudio/vídeo.
     - Aplica imagem de overlay (moldura/marca d'água 16:9) se informada.
5. Emite o evento `clip_done` para o frontend.
6. Salva arquivos consolidados `timestamps.json` e `timestamps.txt`.
7. Apaga o vídeo original completo temporário para liberar disco (se `delete_original_video=True`).
8. Emite evento final `pipeline_finished`.

---

## 4. Tratamento de Erros e Cancelamento

- **Cancelamento:** Verificado via `_check_cancelled()`. Se acionado, interrompe a malha com status `"cancelled"`, removendo arquivos temporários residuais.
- **Exceções Críticas:** Capturadas no worker thread do `ClipperApi`. O erro é formatado em string, gravado nos logs e notificado via evento `pipeline_finished` com `success: False`.
- **Logs:** Redirecionados simultaneamente para o logger nativo do Python e para o array de memória `_recent_logs` (últimas 300 linhas), transmitidos ao cliente via evento `log`.
