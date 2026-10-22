# Serviço Google Gemini — Seleção IA e Metadados

Este documento detalha a implementação do serviço Gemini (`src/services/gemini_service.py`) usado para **seleção semântica de cortes** (Shorts 9:16 e Long Clips 16:9) e **geração de metadados** (título, descrição, tags).

---

## 1. Visão Geral

O serviço atua como uma camada de abstração sobre a **Google Gemini API** com dois caminhos de execução:

| Caminho | Biblioteca | Uso |
|---------|------------|-----|
| **Principal** | `ai` (Vercel AI SDK) | Streaming com validação Pydantic nativa |
| **Fallback** | `requests` REST direto | Chamada HTTP estruturada (`responseSchema`) |

O sistema implementa **cadeia de fallbacks de modelos** (`gemini-3.8-flash` → `gemini-flash-latest` → `gemini-3.5-flash-lite`) e repete a tentativa em ambos os caminhos até obter resposta válida.

---

## 2. Configuração e Chaves

### Variáveis de Ambiente (`.env`)
```env
GEMINI_API_KEY="..."                    # Obrigatória — obtida em https://aistudio.google.com/
GEMINI_MODEL="gemini-3.8-flash"         # Modelo padrão
GEMINI_FALLBACK_MODELS="gemini-3.8-flash,gemini-flash-latest,gemini-3.5-flash-lite"
AI_GATEWAY_API_KEY=""                   # Opcional — se usar Vercel AI Gateway
```

### Resolução de Chave
```python
def get_gemini_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
```

---

## 3. Esquemas de Saída Estruturada (JSON Schema + Pydantic)

### 3.1 Metadados de Vídeo (`GEMINI_VIDEO_DETAILS_SCHEMA`)
```json
{
  "type": "OBJECT",
  "properties": {
    "title": {
      "type": "STRING",
      "description": "Título magnético, ultra específico e contextualizado (máx 60 chars)"
    },
    "description": {
      "type": "STRING",
      "description": "Descrição rica 2-3 frases + pergunta provocativa no final"
    },
    "tags": {
      "type": "ARRAY",
      "description": "6 a 10 hashtags e palavras-chave relevantes",
      "items": {"type": "STRING"}
    }
  },
  "required": ["title", "description", "tags"]
}
```

### 3.2 Seleção de Clipes (`GEMINI_CLIPS_SCHEMA`)
```json
{
  "type": "OBJECT",
  "properties": {
    "clips": {
      "type": "ARRAY",
      "items": {
        "type": "OBJECT",
        "properties": {
          "clip_id": {"type": "INTEGER"},
          "title": {"type": "STRING", "description": "Título chamativo, viral (máx 60 chars)"},
          "hook": {"type": "STRING", "description": "Frase de abertura dos primeiros 3-5s"},
          "reason": {"type": "STRING", "description": "Justificativa narrativa/psicológica"},
          "start_time": {"type": "NUMBER", "description": "Timestamp inicial exato (segundos)"},
          "end_time": {"type": "NUMBER", "description": "Timestamp final exato (segundos)"},
          "viral_score": {"type": "NUMBER", "description": "Potencial viral 0.0 a 10.0"}
        },
        "required": ["clip_id", "title", "hook", "reason", "start_time", "end_time", "viral_score"]
      }
    }
  },
  "required": ["clips"]
}
```

### 3.3 Validação Pydantic
```python
class ClipCandidateItem(BaseModel):
    clip_id: int = Field(default=1)
    title: str = Field(description="Título chamativo, curioso e viral...")
    hook: str = Field(default="", description="Frase ou gancho inicial impactante...")
    reason: str = Field(default="", description="Justificativa narrativa...")
    start_time: float = Field(description="Timestamp exato de início...")
    end_time: float = Field(description="Timestamp exato de término...")
    viral_score: float = Field(default=8.0, description="Nota 0.0 a 10.0")

class ClipsResponse(BaseModel):
    clips: list[ClipCandidateItem] = Field(default_factory=list)

class VideoDetailsResponse(BaseModel):
    title: str = Field(description="Título contextualizado, atrativo e de alto impacto (máx 60 chars)")
    description: str = Field(description="Descrição rica de 2 a 3 frases...")
    tags: list[str] = Field(default_factory=list, description="6 a 10 hashtags relevantes")
```

---

## 4. Duas Rotas de Execução

### 4.1 Vercel AI SDK (Principal)
```python
async def _execute_stream():
    messages = [ai.user_message(prompt)]
    async with ai.stream(ai_model, messages, output_type=output_type) as event_stream:
        async for stream_chunk in event_stream:
            pass
        return event_stream.output
```
- Usa `ai.stream()` com `output_type` (Pydantic model) para validação em tempo real.
- Retorna objeto tipado (`ClipsResponse` ou `VideoDetailsResponse`).

### 4.2 REST Direto (Fallback)
```python
def _call_gemini_rest(
    model_name: str,
    prompt_text: str,
    api_key: str,
    schema: dict | None = None,
    timeout_seconds: int = 120
) -> dict:
    url = f"{GEMINI_API_BASE}/{model_name}:generateContent?key={api_key}"
    generation_config = {
        "temperature": 0.2,
        "responseMimeType": "application/json",
    }
    if schema:
        generation_config["responseSchema"] = schema
    # ... POST request ...
```
- Constrói `responseSchema` nativo do Gemini.
- `temperature: 0.2` para determinismo na seleção.
- Validação manual do JSON retornado.

---

## 5. Seleção de Shorts Verticais (9:16)

### Função: `select_clips_with_gemini()`

**Parâmetros:**
| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `formatted_transcript` | `str` | — | Transcrição completa com marcadores de tempo |
| `video_title` | `str` | — | Título do episódio original |
| `min_duration` | `float` | `20.0` | Duração mínima do clipe (seg) |
| `max_duration` | `float` | `85.0` | Duração máxima do clipe (seg) |
| `max_clips` | `int` | `8` | Quantidade de clipes a retornar |
| `channel_name` | `str` | `""` | Nome do canal/host |
| `video_description` | `str` | `""` | Sinopse do episódio |

**Diretrizes do Prompt (Resumo):**
- **Anti-genérico:** Proíbe títulos clichês ("O segredo de...", "Você não vai acreditar").
- **Âncora na realidade:** Cita pessoas, números, técnicas, situações concretas.
- **Hook imediato:** Início coincide com fala de impacto.
- **Conclusão completa:** Fim após fechamento da ideia/punchline.
- **Diversidade:** Espalha cortes pelo episódio sem sobreposição.
- **Precisão:** Usa timestamps exatos da transcrição fornecida.

---

## 6. Seleção de Cortes Longos (16:9) — Horizontal

### Função: `select_long_clips_with_gemini()`

**Parâmetros específicos:**
| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `min_duration` | `float` | `180.0` | 3 minutos |
| `max_duration` | `float` | `1200.0` | 20 minutos |
| `max_clips` | `int` | `3` | Quantidade de blocos temáticos |

**Foco do Prompt:**
- **Coesão temática total:** Cada clipe é um tema/debate completo (início → meio → fim).
- **Sem cortes abruptos:** Início na introdução do tema; fim na conclusão antes de mudar assunto.
- **Título YouTube:** Informativo e magnético para formato horizontal tradicional.

---

## 7. Geração de Metadados por Clipe

### Função: `generate_video_details()`

Chamada individualmente para cada clipe na etapa de renderização (ou modo `only_timestamps`). Usa a transcrição **apenas do segmento do clipe** (não do vídeo inteiro).

**Prompt direciona:**
1. **Título (≤ 60 chars):** Ultra específico, cita nomes/entidades/números reais do áudio.
2. **Descrição (2-3 frases):** Contextualiza quem fala + resumo inteligente + pergunta final provocativa.
3. **Tags (6-10):** Mix de nome do podcast, temas do corte e keywords do nicho.

---

## 8. Cadeia de Resiliência: Fallbacks de Modelo

```python
models_to_try = [model] + [
    fallback_model for fallback_model in FALLBACK_GEMINI_MODELS if fallback_model != model
]

for candidate_model_name in models_to_try:
    try:
        # 1. Tenta Vercel AI SDK
        sdk_response = _call_vercel_ai_sdk(...)
        if valid: return valid_clips
    except Exception as sdk_error:
        # 2. Tenta REST direto com mesmo modelo
        data = _call_gemini_rest(...)
        if valid: return valid_clips
    # Se ambos falharem, prossegue para próximo modelo
```

**Ordem de prioridade padrão:**
1. `gemini-3.8-flash` (modelo configurado em `GEMINI_MODEL`)
2. `gemini-flash-latest`
3. `gemini-1.5-flash`

Se **todos** os modelos falharem, a exceção final é propagada e o `PipelineEngine` faz fallback automático para **heurísticas estatísticas**.

---

## 9. Integração com o Pipeline

| Etapa do Pipeline | Uso do Gemini |
|-------------------|---------------|
| **Seleção (IA)** | `select_clips_with_gemini()` ou `select_long_clips_with_gemini()` — retorna plano completo com `ai_metadata` anexado a cada segmento. |
| **Metadados (por clipe)** | `generate_video_details()` — chamado na etapa de renderização se não houver `ai_metadata` pré-calculado. |
| **Fallback** | Se `GEMINI_API_KEY` ausente ou erro em todos modelos → `PipelineEngine` loga warning e muda para heurísticas. |

---

## 10. Exemplos de Saída Estruturada

### Seleção de Shorts
```json
{
  "clips": [
    {
      "clip_id": 1,
      "title": "Por que o médico proibiu creatina com café",
      "hook": "Meu médico disse: 'nunca misture creatina com café da manhã'",
      "reason": "Gancho médico contraintuitivo + curiosidade imediata sobre saúde/suplementação",
      "start_time": 145.2,
      "end_time": 205.8,
      "viral_score": 9.2
    }
  ]
}
```

### Metadados de Clipe
```json
{
  "title": "Por que o médico proibiu creatina com café",
  "description": "Neste trecho o Dr. Marcos revela por que a combinação creatina + café da manhã pode sabotar seus ganhos de massa muscular. A explicação bioquímica surpreende até nutricionistas experientes.\n\nVocê já cometeu esse erro no pré-treino?",
  "tags": ["creatina", "musculação", "suplementos", "dr.marcos", "nutricao", "pre-treino", "hipertrofia", "saude"]
}
```

---

## 11. Logs e Debugging

O serviço registra detalhadamente:
```python
logger.info(f"Chamando Vercel AI SDK ({model}) para seleção estruturada...")
logger.warning(f"Tentativa via Vercel AI SDK falhou ({model}): {error}. Tentando fallback REST...")
logger.info(f"Gemini REST ({model}) retornou {len(clips)} sugestões.")
logger.warning(f"Erro ao validar item de clipe do Gemini: {parse_error}")
```

Isso permite diagnosticar:
- Qual modelo foi efetivamente usado.
- Se o fallback REST foi necessário.
- Itens individuais descartados por validação de duração/parsing.
