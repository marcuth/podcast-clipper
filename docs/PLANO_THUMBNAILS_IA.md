# 🎨 Plano de Implementação — Thumbnails com IA (Nano Banana)

> **Status:** Módulo base criado e testado (`src/utils/generate_thumbnail.py`).  
> **Data:** 17 de Outubro de 2026

---

## 1. O que Já Está Pronto e Validado Hoje

1. **Seleção Inteligente do Melhor Frame:**
   - O módulo `src/utils/generate_thumbnail.py` escaneia o vídeo do clipe com `OpenCV` e `MediaPipe`.
   - Pontua automaticamente os frames e **seleciona o momento ideal com os 2 interlocutores visíveis**, nítidos e com expressões expressivas na mesa.
2. **Estratégia Viral com Gemini:**
   - O Gemini analisa o frame + transcrição do corte e gera:
     - **Hook Text:** Frase de 2 a 4 palavras de alto impacto (ex: *"450 NÃO LEEM!"*).
     - **Badge Text:** Selo contextual (ex: `EXPOSTO`, `URGENTE`, `BASTIDORES`).
     - **Cor de Contraste:** HEX chamativo (ex: `#FFE500` amarelo ouro).
     - **Posicionamento:** Escolhe o canto sem cobrir os rostos dos participantes.
3. **Renderização Gráfica YouTube 1280x720:**
   - Realce de contraste e saturação cinematográfica.
   - Vinheta de profundidade nas bordas.
   - Tipografia pesada (`Impact` / `Arial Black`) com **stroke preto de 8px** e **sombra projetada**.
4. **Integração no Backend:**
   - Método `generate_clip_thumbnail(slug, clip_name)` adicionado em `src/gui/api.py`.
   - Adicionados `thumbnail_url` e `thumbnail_path` na listagem de clipes da biblioteca.

---

## 2. Para Usar o "Nano Banana" na Geração da Imagem

### O que descobrimos nos testes:
Os modelos multimodais de imagem existem na API do Google:
- `models/gemini-nano-banana-2.1`
- `models/nano-banana-pro-preview`
- `models/gemini-3.1-flash-image`
- `models/gemini-2.5-flash-image`

No teste de chamada direta, a API retornou:
> **Status 429:** *"You exceeded your current quota, please check your plan and billing details."*

### O que você precisa fazer depois:
1. **Ativar o Faturamento (Billing) no Google AI Studio:**
   - Acessar [ai.google.dev](https://ai.google.dev/) e vincular uma conta de faturamento (GCP Billing) ao projeto da chave de API.
   - Os modelos de geração e edição de imagem exigem cota com billing habilitado (ao contrário dos modelos de texto como `gemini-3.8-flash`, que têm cota gratuita ampla).
2. **(Opcional) Provedor Alternativo de Image-to-Image:**
   - Se preferir não usar o Google para geração de imagens, podemos plugar APIs especializadas como **fal.ai**, **Replicate (Flux Schnell / Inpainting)** ou **OpenAI (DALL-E 3)** com 1 única linha no `.env`.

---

## 3. Como Remover QR Codes e Overlays Nativos da Transmissão

Para deixar a imagem 100% limpa (sem superchats, QR codes e logos antigos do estúdio), definimos 2 soluções que implementaremos:

### Abordagem A: Re-framing & Inpainting Local (100% Gratuito e Offline)
- **Corte de Faixa Inferior:** Os QR codes e superchats do podcast original ficam concentrados nos **últimos 14% da base da tela** (Y > 86%).
- Re-enquadramos o frame cortando essa faixa inferior e centralizando os interlocutores em proporção 16:9 widescreen limpa.
- Onde houver marcas d'água restantes, o algoritmo de `cv2.inpaint` preenche a textura do fundo da mesa.
- Em seguida, a nossa própria moldura (`Moldura CastClipes`) é aplicada na base, cobrindo com visual profissional.

### Abordagem B: Image-to-Image / Inpainting via Nano Banana
- Enviamos o frame com a máscara dos cantos inferiores para o `gemini-nano-banana-2.1` com o prompt:
  > *"Remove lower thirds, watermark, superchat overlay and QR code from the bottom of this podcast frame. Reconstruct the microphone, studio table and background with realistic lighting while preserving the exact facial identity of both speakers."*

---

## 4. Próximos Passos na Interface (Frontend)

1. **Card de Clipes na Biblioteca:**
   - Exibir o preview da thumbnail em formato 16:9 no topo do card (com opção de alternar entre vídeo e thumbnail).
2. **Botão de Ação Rápida:**
   - Botão **"Gerar Thumbnail com IA"** com seletor de estilo (Nano Banana / Estúdio Limpo / Clássico).
3. **Publicação no YouTube:**
   - O `YouTubeService.upload_clip` já aceita `thumbnail_path`. Basta passar a thumbnail gerada automaticamente no momento da publicação.

---

*Descanse bem! Tudo está salvo, o código está compilando sem nenhum erro e pronto para continuarmos amanhã.*
