# Processamento de Vídeo, Renderização e Legendas

Este documento detalha os algoritmos de **detecção facial (MediaPipe)**, **layout split-screen**, **enquadramento 9:16**, **legendas animadas ASS**, **remoção de silêncios por FFmpeg** e **efeitos visuais** implementados no AutoClip Studio.

---

## 1. Visão Geral dos Módulos

| Módulo | Arquivo | Responsabilidade |
|--------|---------|------------------|
| **Corte Shorts 9:16** | `src/utils/cut_clip.py` | Crop dinâmico face-tracking, split-screen, vinheta, música de fundo, renderização FFmpeg |
| **Corte Longo 16:9** | `src/utils/cut_long_clip.py` | Detecção de silêncio por FFmpeg (`silencedetect`), corte sem perdas de áudio, overlay 16:9 |
| **Detecção Facial** | `src/utils/detect_face_center.py` | MediaPipe `blaze_face_short_range.tflite` para detecção de até 2 rostos |
| **Legendas Animadas** | `src/utils/generate_subtitles.py` | Gerador de arquivo `.ass` com efeito pop-in/elastic bounce estilo CapCut |
| **Re-transcrição de Clipe** | `src/utils/transcribe_clip.py` | Whisper local no clipe individual para alinhamento milimétrico de texto |

---

## 2. Detecção Facial com MediaPipe (`detect_face_center.py`)

A detecção facial utiliza o modelo ultra-leve e rápido `blaze_face_short_range.tflite` localizado em `models/`.

### Algoritmo `detect_faces()`
1. Recebe um quadro BGR do OpenCV e converte para `mp.Image`.
2. Executa a detecção com confiança mínima $0.45$.
3. Filtra caixas delimitadoras (*bounding boxes*) menores que $25 \times 25$ px (ruídos de fundo).
4. Calcula o centro horizontal ($c_x$) e vertical ($c_y$) de cada rosto.
5. **Classificação de 2 Pessoas (Podcast Layout):**
   - Ordena os rostos por área decrescente.
   - O segundo rosto é aceito somente se sua área for $\ge 20\%$ da área do primeiro rosto **E** a distância horizontal entre eles for $\ge 10\%$ da largura total do vídeo.
   - Se ambas as condições forem atendidas, re-ordena os 2 rostos da esquerda para a direita ($c_{x1} < c_{x2}$).

```python
# Retorna lista de 0, 1 ou 2 rostos ordenados por cx:
# [{'cx', 'cy', 'x', 'y', 'w', 'h', 'score', 'area'}]
```

---

## 3. Enquadramento e Animação de Câmera (Shorts 9:16)

### 3.1 Amostragem e Filtro de Suavização (Exponential Smoothing)
Para evitar movimentos brutos ou "tremidos" de câmera quando a pessoa se mexe levemente:

1. **Amostragem Rápida (`sample_frames_fast`):** Lê o vídeo a 5 FPS extraindo os rostos presentes.
2. **Suavização Exponencial (`smooth_positions`):**
   - Aplica interpolação ponderada entre o ponto atual $P_t$ e o último ponto $P_{\text{last}}$ com fator $\alpha = 0.1$:

$$P_{\text{smoothed}} = \alpha \cdot P_t + (1 - \alpha) \cdot P_{\text{last}}$$

   - **Detecção de Mudança de Tomada (Cut Detection):** Se o salto no espaço for $> 100\text{px}$ ou o tempo sem rosto for $> 1.0\text{s}$, desativa o filtro momentaneamente e salta a câmera imediatamente para a nova posição (corte seco de câmera).

---

### 3.2 Layout Split-Screen para 2 Pessoas
Quando duas pessoas estão conversando no podcast:

1. **Ativação:** Se a razão de quadros com 2 rostos detectados for $\ge 20\%$ do clipe, o sistema realiza um sorteio probabilístico baseado em `split_screen_chance` (padrão 50%).
2. **Construção dos Blocos (Top & Bottom):**
   - **Bloco Superior (Pessoa 1 - Esquerda):** Recorta a câmera focada em $(c_{x1}, c_{y1})$.
   - **Bloco Inferior (Pessoa 2 - Direita):** Recorta a câmera focada em $(c_{x2}, c_{y2})$.
   - Redimensiona ambos os blocos para $1080 \times 958$ px.
   - Insere uma linha divisória escura de 4px na cor `#141823` no centro.
   - Empilha os blocos verticalmente (`np.vstack`) formando o arquivo final $1080 \times 1920$ px.

---

## 4. Legendas Animadas com Efeito Pop-in / CapCut (`generate_subtitles.py`)

As legendas são gravadas diretamente no vídeo (*burned-in*) via filtro `subtitles` do FFmpeg usando o formato **Advanced SubStation Alpha (.ass)**.

### 4.1 Animação ASS Pop-in (Elastic Bounce)
Para cada palavra ou pedaço de frase (*chunk* de 2 palavras ou máximo 12 caracteres), gera-se a tag inline de animação escalar:

```ass
{\fscx0\fscy0\t(0,100,\fscx120\fscy120)\t(100,180,\fscx100\fscy100)}TEXTO EM MAIÚSCULAS
```

- `\fscx0\fscy0`: inicia com escala $0\%$ (invisível).
- `\t(0,100,\fscx120\fscy120)`: expande rapidamente até $120\%$ em $100\text{ms}$ (efeito de estouro/pop).
- `\t(100,180,\fscx100\fscy100)`: desacelera e estabiliza em $100\%$ entre $100\text{ms}$ e $180\text{ms}$.

### 4.2 Estilo CapCut Utilizado
```ini
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CapCut,Poppins,115,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,0,2,10,10,650,1
```
- **Fonte:** Poppins (tamanho 115)
- **Cores:** Texto branco (`&H00FFFFFF`), contorno preto espesso (`Outline: 6`), sombra suave
- **Alinhamento:** Centralizado na parte inferior (`Alignment: 2`, `MarginV: 650`)

---

## 5. Efeitos Visuais e Áudio em Shorts (9:16)

### 5.1 Efeito Vinheta (Escurecimento de Bordas)
Adiciona profundidade focando o olhar no centro do clipe.
- Parâmetro FFmpeg: `vignette={vignette_angle}:aspect=9/16`
- Ângulos:
  - `"PI/5"` (Suave)
  - `"PI/4"` (Moderado — Padrão)
  - `"PI/3.5"` (Intenso / Cinemático)

### 5.2 Música de Fundo Aleatória
- Varre a pasta `assets/audios/musics/` em busca de arquivos `.mp3`.
- Seleciona uma faixa aleatória e aplica corte temporal aleatório.
- Reduz o volume para `0.1` ($10\%$) e mistura com o áudio original das vozes via `CompositeAudioClip`.

---

## 6. Remoção de Silêncios por FFmpeg em Cortes Longos 16:9 (`cut_long_clip.py`)

Para vídeos horizontais de debate no YouTube tradicional, o sistema utiliza o algoritmo de **Jump Cut Inteligente** baseado no filtro `silencedetect` do FFmpeg.

### 6.1 Detecção de Silêncio (`detect_silences_ffmpeg`)
Executa o FFmpeg em modo nulo e analisa as mensagens no `stderr`:

```bash
ffmpeg -i video.mp4 -af silencedetect=noise=-30dB:d=0.6 -f null -
```

Retorna lista de intervalos mudos: `[(start_1, end_1), (start_2, end_2), ...]`.

---

### 6.2 Cálculo de Intervalos de Fala (`calculate_speech_intervals`)
Inverte os intervalos de silêncio para obter os blocos com áudio, adicionando uma **margem de segurança** (`silence_padding = 0.15s`) antes e depois de cada trecho de fala. Isso garante que respirações naturais e inícios de palavras não sejam cortados secamente.

---

### 6.3 Concatenação e Overlay
1. Extrai cada segmento falado via FFmpeg sem re-encodagem desnecessária.
2. Concatena todos os trechos falados através de um arquivo de lista de concatenação do FFmpeg (`concat demuxer`).
3. Se um arquivo de overlay 16:9 (imagem PNG com transparência) for especificado:
   - Aplica o overlay via filtro complexo: `[0:v][1:v]overlay=0:0[outv]`.
4. Renderiza o arquivo final em H.264/AAC.

---

## 7. Parâmetros de Renderização FFmpeg (Saída Final)

Para garantir máxima compatibilidade com TikTok, Instagram Reels e YouTube Shorts:

```python
ffmpeg_params = [
    "-crf", "18",                # Altíssima qualidade visual (CRF 18)
    "-pix_fmt", "yuv420p",       # Formato de cor universal para dispositivos móveis
    "-profile:v", "high",
    "-level", "4.0",
    "-movflags", "+faststart",   # Permite reprodução instantânea via web streaming
]
```
- **Codec de Vídeo:** `libx264` (preset `medium`, 24 FPS)
- **Codec de Áudio:** `aac` (192 kbps)
