# Heurísticas de Pontuação e Heatmap

Este documento descreve as 8 regras estatísticas de pontuação e o cálculo do **Heatmap do YouTube** utilizados pelo motor de heurísticas (`src/heuristics/`) para identificar momentos virais sem depender de LLMs.

---

## 1. Conceito do Scoring de Segmentos

Cada trecho de transcrição é representado por uma instância do modelo `Segment` (`src/domain/segment.py`):

```python
@dataclass
class Segment:
    start: float     # tempo de início em segundos
    end: float       # tempo de término em segundos
    text: str        # texto original
    norm: str        # texto em minúsculas sem pontuação
    score: float = 0.0
```

No modo heurístico (`STRATEGY_HEURISTICS`), a função `apply_heuristics()` muta o atributo `segment.score` **in-place** aplicando uma sequência de regras aditivas e penalidades.

---

## 2. As 8 Heurísticas de Pontuação

### 1. Gatilhos de Atenção (`score_triggers.py`)
Identifica palavras e expressões frequentemente usadas antes de revelações, conselhos ou declarações impactantes.

```python
TRIGGERS_REGEX = re.compile(
    r"(presta atenção|olha só|o ponto é|o problema é|"
    r"ninguém fala sobre|o maior erro|o segredo é|"
    r"o que ninguém te conta|isso muda tudo|isso é importante|"
    r"você sabia|a verdade é|muita gente|inacreditável|"
    r"surpreendente|dica de ouro|conselho|essa história)",
    re.IGNORECASE
)
```
- **Bônus:** `+1.0` se encontrar qualquer gatilho.

---

### 2. Contraste e Virada Semântica (`score_contrast.py`)
Detecta a estrutura narrativa "antes vs. agora" ou quebra de expectativa ("todo mundo acha X, mas Y").

```python
CONTRAST = re.compile(r"(antes.*agora)|(todo mundo.*mas)|(parecia.*mas)")
```
- **Bônus:** `+0.7` se houver virada de contraste.

---

### 3. Perguntas Retóricas (`score_question.py`)
Perguntas geram curiosidade e retenção imediata.

```python
if segment.text.strip().endswith("?"):
    segment.score += 0.4
```
- **Bônus:** `+0.4` se o segmento terminar com interrogação.

---

### 4. Tamanho da Frase ("Tweetável") (`score_length.py`)
Frases de tamanho médio (8 a 20 palavras) tendem a ser declarações assertivas e fáceis de memorizar.

```python
word_count = len(segment.text.split())
if 8 <= word_count <= 20:
    segment.score += 0.3
```
- **Bônus:** `+0.3` para contagem de palavras entre 8 e 20.

---

### 5. Histórias Pessoais e Conexão (`score_personal.py`)
Frases em primeira pessoa reforçam storytelling e vulnerabilidade.

```python
PERSONAL_REGEX = re.compile(
    r"\b(eu|meu|minha|a gente|nós|fiquei|pensei|achei|senti|falei)\b",
    re.IGNORECASE
)
```
- **Bônus:** `+0.5` se contiver pronomes ou verbos em 1ª pessoa.

---

### 6. Mudança de Ritmo / Pausa Prévia (`score_pause.py`)
Uma pausa antes da fala sinaliza que o interlocutor respirou ou pensou antes de dizer algo relevante.

```python
gap = curr.start - prev.end
if prev and gap > 0.4:
    curr.score += 0.2
```
- **Bônus:** `+0.2` se o intervalo em relação ao segmento anterior for maior que `0.4s`.

---

### 7. Penalidade de CTA / Encerramento (`score_cta.py`)
Descarta chamadas para ação (pedidos de inscritos, likes, patrocinadores) e despedidas que quebram o ritmo do clipe.

```python
CTA_REGEX = re.compile(
    r"(inscrev(a|e)-?se|inscreve|aqui nos comentários|deixa o like|dar o like|curte o vídeo|"
    r"ativa o sininho|segue a gente|compartilha esse vídeo|comenta (aqui embaixo|aí)|"
    r"link na (descrição|bio)|assista(m)? os outros|vídeo aqui na tela|tchau|até o próximo|"
    r"valeu pessoal|não esquece de|se você gostou|espero que vocês tenham gostado|tela final|hype)",
    re.IGNORECASE
)
```
- **Penalidade:** `-100.0` (garante que o segmento seja desconsiderado).

---

### 8. Penalidade Temporal e Duplicatas (`score_time.py`)
Evita vinhetas/intros do canal e corrige possíveis erros de timestamp.

```python
if segment.start == last_segment.start:
    segment.score -= 100.0
elif segment.start < 60:
    segment.score -= 100.0
```
- **Penalidade:** `-100.0` para trechos no primeiro minuto ($< 60s$) ou com início igual ao último segmento.

---

## 3. Boost de Retenção com Heatmap do YouTube (`score_heatmap.py`)

O YouTube disponibiliza publicamente a curva de retenção de audiência ("mais reproduzido"). A função `get_youtube_heatmap()` extrai essa curva via `yt-dlp`.

### Algoritmo do Heatmap
1. A curva do YouTube é representada por uma lista de janelas de tempo, cada uma com uma intensidade normalizada entre `0.0` e `1.0`:
   ```python
   [{"start": 120.0, "end": 125.0, "intensity": 0.85}, ...]
   ```
2. Para cada segmento, identifica-se todas as janelas do heatmap que sobrepõem o tempo do segmento (`overlap_end > overlap_start`).
3. Calcula-se a intensidade média das sobreposições: $\text{avg\_intensity}$.
4. Aplica-se o bônus ponderado:

$$\text{score} \leftarrow \text{score} + (\text{HEATMAP\_BOOST} \times \text{avg\_intensity})$$

onde $\text{HEATMAP\_BOOST} = 3.0$.

Se a intensidade for máxima ($1.0$), o segmento ganha **+3.0 pontos**, tornando trechos muito reassistidos extremamente propensos a virarem cortes.

---

## 4. Agrupamento em Clipes (`create_clips.py`)

Após a pontuação de todos os segmentos, o utilitário `create_clips()` transforma a lista plana em clipes coesos:

1. **Filtragem:** Remove segmentos com pontuação $< -50$.
2. **Fusão por Proximidade:** Agrupa segmentos sequenciais que possuem intervalo de tempo $\le 1.5s$ (`CLIP_GAP`).
3. **Validação de Duração:**
   - Descarta grupos com duração $< 15s$.
   - Grupos de até $60s$ são mantidos intactos.
   - Grupos $> 60s$ são divididos pela função `find_best_subclips()`, que busca sub-janelas de $15s$ a $60s$ que maximizam a soma das pontuações sem sobreposição.
4. **Ranking:** Ordena todos os candidatos pela soma dos pontos, seleciona os Top `max_clips` (padrão 8 a 10) e re-ordena cronologicamente por horário de início.
