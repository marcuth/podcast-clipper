# Interface de Linha de Comando (CLI)

O **AutoClip Studio** possui um modo interativo em linha de comando (`CLI`), alimentado pela biblioteca `questionary`, permitindo executar todo o pipeline de automação diretamente do terminal sem abrir a interface gráfica desktop.

---

## 1. Execução do CLI

Para iniciar o pipeline no modo CLI:

```bash
poetry run start
# OU
poetry run python src/main.py
```

---

## 2. Fluxo Interativo de Configuração

Ao executar o comando, o terminal guiará o usuário passo a passo pelas seguintes perguntas:

### Passo 1: URL do Vídeo do YouTube
```text
Enter YouTube video URL: https://www.youtube.com/watch?v=...
```
- Valida o link informado através de expressão regular (`youtube.com` ou `youtu.be`).
- Em caso de URL inválida, solicita a digitação novamente.

---

### Passo 2: Estratégia de Seleção dos Melhores Cortes
```text
? Como deseja selecionar os melhores cortes do vídeo?
  🤖 Inteligência Artificial (Gemini API - analisa narrativa e ganchos) [Recomendado]
  📊 Heurísticas & Estatísticas (Regras de palavras-chave + Heatmap)
```

---

### Passo 3: Modo de Obtenção da Transcrição
```text
? How do you want to get the transcription?
  Local Whisper (Slower, but more accurate)
  YouTube Captions – full download (Fast)
  YouTube Captions – partial download (Fastest, downloads only needed clips)
```

---

### Passo 4: Formato de Processamento do Vídeo
```text
? Como deseja processar os clipes?
  🎬 Shorts Verticais 9:16 (.mp4 + enquadramento facial + legendas)
  📺 Cortes Longos 16:9 (.mp4 horizontal + remoção de silêncio + overlay)
  ⏱️ Apenas gerar timestamps e metadados (Ultra rápido - sem renderizar vídeos)
```

---

### Passo 5: Configurações Específicas por Formato

#### Se selecionado Shorts Verticais (9:16):
1. **Legendas Queimadas:**
   ```text
   ? Renderizar legendas dinâmicas no vídeo? (burned-in subtitles) (Y/n)
   ```
2. **Re-transcrição com Whisper:** (se selecionado legendas do YouTube)
   ```text
   ? Re-transcribe each clip with Whisper for accurate subtitles? (Y/n)
   ```
3. **Efeito Vinheta:**
   ```text
   ? Apply vignette effect (darken video borders/edges)? (Y/n)
   ```
   Se ativado:
   ```text
   ? Vignette intensity:
     Moderate (Recommended - PI/4)
     Subtle (Soft - PI/5)
     Intense (Cinematic - PI/3.5)
   ```
4. **Split-Screen Dinâmico (2 Pessoas):**
   ```text
   ? Dividir tela em 2 blocos (split-screen) quando houver 2 pessoas conversando? (Y/n)
   ```
   Se ativado:
   ```text
   ? Chance de aplicar split-screen em tomadas com 2 pessoas:
     50% (Equilibrado / Dinâmico - Padrão)
     100% (Sempre dividir quando houver 2 pessoas)
     30% (Ocasional / Mais raro)
   ```

#### Se selecionado Cortes Longos (16:9):
1. **Remoção de Silêncios:**
   ```text
   ? Remover pausas de silêncio automaticamente (Jump Cut FFmpeg)? (Y/n)
   ```
2. **Overlay de Marca d'Água:**
   ```text
   ? Deseja aplicar overlay nos cortes longos?
     Sim, usar overlay padrão (frame.png)
     Sim, informar outro arquivo de imagem (PNG/JPG)
     Não aplicar overlay
   ```

---

### Passo 6: Quantidade Máxima de Cortes
```text
Quantidade máxima de cortes a extrair (1 a 15) [8]:
```
- Padrão: 8 cortes para Shorts ou 3 cortes para vídeos Longos.

---

## 3. Saída de Logs no Terminal

Durante a execução, o CLI utiliza o logger nativo do Python e exibe mensagens formatadas com timestamp:

```text
2026-10-16 23:45:01,123 - INFO - Initializing Application
2026-10-16 23:45:02,456 - INFO - [METADATA - 5%] Obtendo informações do vídeo...
2026-10-16 23:45:03,789 - INFO - Vídeo identificado: 'PodCast Especial #100'
2026-10-16 23:45:05,012 - INFO - [HEATMAP - 15%] Coletando heatmap do YouTube...
2026-10-16 23:45:07,345 - INFO - [TRANSCRIBE - 40%] Transcrevendo conteúdo do vídeo...
2026-10-16 23:45:12,678 - INFO - [HEURISTICS - 55%] IA (Gemini) analisando momentos virais...
2026-10-16 23:45:15,901 - INFO - [CUTTING - 60%] Processando clipe 1 de 8 (45.2s)...
...
2026-10-16 23:46:30,123 - INFO - 🎉 Pipeline finalizado com sucesso! Pasta: output/podcast-especial-100
```

Os resultados são salvos em `output/<slug>/` e podem ser visualizados posteriormente na interface gráfica abrindo a aba **Biblioteca de Projetos** (`poetry run gui`).
