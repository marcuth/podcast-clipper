# Conceitos da Interface Atual — AutoClip Studio

Este documento reúne todos os conceitos, regras de negócio, fluxos de usuário, campos, estados e integrações da interface gráfica atual do **AutoClip Studio**.
Utilize este arquivo como referência para editar, remover, expandir ou redesenhar qualquer componente antes da implementação no novo frontend em **React + TypeScript + Vite + Shadcn/ui**.

---

## 1. Visão Geral da Aplicação e Arquitetura

- **Hospedagem & Janela:** Aplicação desktop rodando através do `pywebview` (`src/gui/app.py`), com janela nativa do Windows (1320x880 px, tema escuro).
- **Servidor Interno:** Servidor HTTP local baseado em `Bottle` (`src/gui/server.py`), responsável por:
  - Servir a interface web compilada (`/`).
  - Fazer streaming de vídeo com suporte a *HTTP Range Requests* (`/media/<slug>/clips/<video>.mp4`) para permitir scrubbing instantâneo na timeline do player.
- **Ponte de Comunicação (Bridge):**
  - **JS -> Python:** Chamadas assíncronas via `window.pywebview.api.<metodo>()` retornando Promises.
  - **Python -> JS:** Eventos push em tempo real enviados via `window.__clipperBridge.emit(event, data)`.

---

## 2. Cabeçalho Global (Header)

- **Identidade Visual:** Logo com gradiente + Título `AutoClip AI` + Subtítulo `Podcast & Video Shorts Automation`.
- **Navegação por Abas:**
  1. **Estúdio de Shorts (9:16):** Foco em vídeos verticais dinâmicos para TikTok, YouTube Shorts e Reels.
  2. **Cortes Longos (16:9):** Foco em vídeos panorâmicos para o YouTube, blocos de conversas e debates com eliminação de silêncios.
  3. **Biblioteca de Clipes:** Galeria de projetos gerados com players, edição de metadados e cópia rápida.
  4. **Diagnóstico:** Status de saúde do sistema, chaves de API e caminhos locais.
- **Pill de Status do Sistema:** Indicador visual no topo (`Pronto`, `Em execução...`, `Concluído`, `Cancelado`, `Erro`).

---

## 3. Aba 1: Estúdio de Shorts (9:16)

### 3.1. Formulário de Entrada do Vídeo
- **Campo de URL:** Input para link do YouTube (`https://www.youtube.com/watch?v=...` ou `https://youtu.be/...`).
- **Botão "Colar":** Lê a área de transferência do sistema operacional e preenche o campo.
- **Botão "Buscar Vídeo":** Executa `api.get_video_info(url)`.
- **Card de Pré-visualização do Vídeo (Aparece após busca):**
  - Thumbnail grande do vídeo com badge de duração formatada (`HH:MM:SS`).
  - Nome do canal / autor.
  - Título do vídeo.
  - Contagem de visualizações e badge de validação.

### 3.2. Estratégia de Seleção dos Melhores Cortes
- **✨ IA Gemini (Recomendado):** Análise semântica da transcrição completa do episódio. Detecta momentos surpreendentes, ganchos (hooks), discussões acaloradas e conclusões de raciocínio.
- **📊 Heurísticas & Heatmap (Estatístico):** Abordagem estatística clássica. Pontua trechos avaliando perguntas, gatilhos de contraste, pausas de áudio e picos de repetição da audiência do YouTube.

### 3.3. Modo de Download & Transcrição
- **⚡ Legendas YouTube (Parcial) [Muito Lento, Menos Banda]:** Não baixa o vídeo inteiro. Obtém a legenda oficial do YouTube, calcula os cortes ideais e faz download somente dos trechos necessários (ex: 30 a 90 segundos cada). É muito lento, mas economiza cerca de 90% de banda.
- **⚖️ Legendas YouTube (Completo) [Balanceado]:** Baixa o vídeo completo em 720p e usa as legendas oficiais do YouTube para a análise.
- **🎯 Local Whisper (IA Local) [Alta Precisão]:** Baixa o áudio completo e executa o modelo `Faster-Whisper` localmente. Ideal para vídeos sem legendas no YouTube ou com legendas geradas automaticamente de baixa qualidade.

### 3.4. Opções e Otimizações Virais (Toggles)
- **🔥 Impulso com Heatmap do YouTube:** Consulta a curva de retenção pública do YouTube ("mais reproduzido") e amplifica o score de viralidade dos trechos que o público mais assistiu.
- **🔤 Renderizar Legendas no Vídeo:** Grava (queima) legendas dinâmicas animadas diretamente no clipe vertical. Se desativado, produz cortes limpos.
- **✍️ Re-transcrever Legendas com Whisper:** Mesmo usando legendas do YouTube para pontuação, roda o Whisper apenas nos cortes finais selecionados para sincronização milimétrica palavra por palavra.
- **👥 Split-Screen Dinâmico (2 Pessoas):** Roda detecção facial via MediaPipe e divide a tela em dois blocos verticais empilhados (layout podcast com duas pessoas conversando).
- **⏱️ Apenas Timestamps & Metadados:** Não baixa nem renderiza nenhum vídeo. Apenas calcula os pontos exatos de corte (início/fim) e gera títulos, descrições e ganchos com IA (modo ultra-rápido para quem edita manualmente no Premiere/CapCut).

### 3.5. Ação de Início
- **Botão "Gerar Clipes com IA":** Dispara `api.start_pipeline(...)`. O botão fica desabilitado durante o processamento.

### 3.6. Painel de Monitoramento em Tempo Real
- **Cabeçalho:** Título "Processamento em Tempo Real" + Botão "Cancelar".
- **Stepper de Fases (6 etapas visuais com ícones):**
  1. *Metadados* (Extração de informações do vídeo).
  2. *Heatmap* (Coleta de picos de audiência).
  3. *Preparação* (Download / extração de áudio).
  4. *Transcrição* (Processamento Whisper ou legendas).
  5. *Heurísticas / IA* (Seleção dos momentos de maior impacto).
  6. *Renderização* (Corte, enquadramento de rosto, split-screen e legendas).
- **Barra de Progresso:** Porcentagem dinâmica (0% a 100%) e texto da operação atual.
- **Console / Terminal de Logs:** Visualização em tempo real das mensagens geradas pelo backend Python, com cores por nível de log (info, warning, error) e botão para limpar histórico.

---

## 4. Aba 2: Cortes Longos (16:9 Panorâmico)

Especialmente projetada para canais de cortes no YouTube tradicional (vídeos horizontais de debate, entrevistas completas e histórias de 3 a 20 minutos).

### 4.1. Entrada do Vídeo
- Entrada de URL do YouTube, botão de colar e botão de buscar vídeo com card de preview (marcado com tags `16:9 Horizontal Nativo` e `Sem Legenda Queimada`).

### 4.2. Modo de Seleção do Corte Longo
- **✨ IA Gemini (Recomendado):** A IA lê toda a transcrição e identifica tópicos fechados de discussão (início da pergunta até o encerramento do tema).
- **⏱️ Intervalo Personalizado:** O usuário insere manualmente o tempo inicial (`HH:MM:SS` ou `MM:SS`) e final desejado.

### 4.3. Parâmetros de Duração e Quantidade (Modo IA)
- **Duração Mínima:** Slider de 2 a 15 minutos (padrão: 3 min). Cortes mais curtos são descartados.
- **Duração Máxima:** Slider de 5 a 20 minutos (padrão: 15 min).
- **Quantidade de Cortes:** Slider de 1 a 5 blocos de conversa distintos.

### 4.4. Motor de Detecção e Corte de Silêncios (Jump Cut Inteligente)
- **Toggle Liga/Desliga:** Ativa ou desativa a eliminação de silêncios por FFmpeg.
- **Presets de Sensibilidade:**
  - *Suave (-35 dB):* Corta apenas silêncios absolutos e vazios longos.
  - *Padrão (-30 dB):* Configuração balanceada para ritmo dinâmico sem cortar respirações naturais.
  - *Agressivo (-25 dB):* Ritmo acelerado de alta retenção.
- **Ajustes Finos (Sliders):**
  - *Limite de Ruído (Threshold):* -45 dB a -20 dB.
  - *Duração Mínima da Pausa:* 0.3s a 1.5s.
  - *Margem de Segurança (Padding):* 50ms a 300ms (tempo preservado antes e depois de cada fala para evitar cortes secos).

### 4.5. Monitoramento do Corte Longo
- Stepper específico:
  1. Metadados → 2. Heatmap → 3. Preparação → 4. Transcrição → 5. Temas Longos → 6. Silêncio & Render.
- Barra de progresso e terminal dedicado.

---

## 5. Aba 3: Biblioteca de Clipes (Library)

### 5.1. Barra de Controle do Projeto
- **Seletor de Projetos:** Dropdown listando todas as pastas em `output/`, ordenadas pela mais recente. Mostra ícone indicativo (`🎬` para vídeos renderizados ou `⏱️` para projetos de apenas timestamps) e a quantidade de cortes.
- **Botão "Atualizar":** Recarrega a lista de projetos do disco.
- **Botão "Abrir Pasta do Projeto":** Abre a pasta do projeto no Windows Explorer nativo via `api.open_folder(...)`.

### 5.2. Grid de Clipes
Apresenta os cortes do projeto selecionado em cards responsivos:

#### Tipo A: Clipe Renderizado (com Vídeo MP4)
- **Player de Vídeo Embutido:** Tag `<video>` com controles nativos, reproduzindo a rota `/media/<slug>/clips/clip_XX.mp4`.
- **Badges sobrepostas:** Pontuação de viralidade (ex: `★ 8.7`) e Duração (`MM:SS`).
- **Título do Corte:** Input editável com o título sugerido pela IA.
- **Descrição & Ganchos:** Textarea editável com o texto gerado pela IA para publicação.
- **Hashtags:** Pílulas com as tags sugeridas (ex: `#podcast #cortes`).
- **Ações do Card:**
  - *Salvar:* Grava as alterações no arquivo `clip_XX_details.json` através de `api.update_clip_details(...)`.
  - *Copiar:* Copia para a área de transferência o título formatado, descrição completa e hashtags prontas para postar.
  - *Abrir no Player Externo:* Abre o arquivo `.mp4` no player de vídeo padrão do Windows (VLC, Media Player, etc.) via `api.open_video(...)`.

#### Tipo B: Clipe de Apenas Timestamps
- **Painel Visual de Timestamps:** Exibe badge `⏱️ Apenas Timestamps` e Score.
- **Bloco de Horários:** Horário de Início (`HH:MM:SS`) → Seta → Horário de Fim (`HH:MM:SS`), com a duração total calculada.
- **Gancho (Hook) Destacado:** Citação do momento de abertura sugerido pela IA.
- **Edição de Título e Descrição:** Campos editáveis e botão Salvar.
- **Copiar Timestamps & Metadados:** Copia os horários exatos e metadados para colar em roteiros ou programas de edição.

---

## 6. Aba 4: Diagnóstico & Configurações

### 6.1. Itens de Diagnóstico
- **Google Gemini API:** Indica se a chave está configurada e exibe preview da chave (`AIza...1234`). Permite digitar uma nova chave e salvá-la diretamente no `.env` do projeto via `api.save_gemini_api_key(...)`.
- **Modelo de Rastreamento Facial:** Checa se o arquivo `models/blaze_face_short_range.tflite` existe para enquadramento inteligente e split-screen.
- **Ambiente de Execução:** Versão do Python detectada.
- **Diretório de Saída:** Caminho absoluto da pasta `output/` com botão para abri-la no Explorer.

### 6.2. Dicas de Produtividade
- Recomendações de uso (modo parcial para episódios longos, relevância do heatmap, benefícios da retranscrição com Whisper).

---

## 7. Mapeamento de Eventos e Métodos da API Bridge

### Métodos Disponíveis em `window.pywebview.api`:
| Método | Parâmetros | Retorno | Descrição |
|---|---|---|---|
| `get_video_info` | `url: string` | `{ success: boolean, data?: VideoInfo, error?: string }` | Obtém metadados do YouTube sem download |
| `start_pipeline` | `options: PipelineOptions` | `{ success: boolean, message?: string, error?: string }` | Inicia o pipeline em thread de background |
| `cancel_pipeline` | *nenhum* | `{ success: boolean, message: string }` | Sinaliza cancelamento para a thread |
| `get_status` | *nenhum* | `{ is_running: boolean, progress: ProgressData, logs: LogItem[] }` | Consulta status atual do pipeline |
| `get_projects` | *nenhum* | `ProjectItem[]` | Lista pastas geradas em `output/` |
| `get_project_clips` | `slug: string` | `ClipItem[]` | Lista todos os clipes e metadados de um projeto |
| `update_clip_details` | `slug: string, clip_name: string, details: ClipDetails` | `{ success: boolean, message?: string, error?: string }` | Salva alterações em `_details.json` |
| `open_folder` | `target_path: string` | `boolean` | Abre pasta no Windows Explorer |
| `open_video` | `video_path: string` | `boolean` | Abre vídeo no player padrão do Windows |
| `get_system_info` | *nenhum* | `SystemInfo` | Checa chaves de API, modelos e ambiente |
| `save_gemini_api_key` | `api_key: string` | `{ success: boolean, message?: string, error?: string }` | Salva a chave no arquivo `.env` |

### Eventos Emitidos pelo Backend via `window.__clipperBridge.emit(event, data)`:
| Evento | Payload (`data`) | Descrição |
|---|---|---|
| `'progress'` | `{ step: string, step_index: number, percentage: number, message: string, current_clip: number, total_clips: number, data: object }` | Atualização do stepper e barra de progresso |
| `'log'` | `{ level: "info" \| "warning" \| "error", message: string }` | Nova linha de log emitida pelo Python |
| `'clip_done'` | `{ name: string, score: number, ... }` | Notificação disparada assim que um corte termina |
| `'pipeline_finished'` | `{ success: boolean, result?: object, error?: string }` | Notificação de encerramento do processo |

---

## 8. Oportunidades de Melhoria para a Nova Interface (React + Shadcn/ui)

- **Design System Consistente:** Substituir CSS manual por componentes Shadcn/ui (Tabs, Dialogs, Cards, Badges, Sliders, Switches, Accordions, Toasts/Sonner, ScrollArea, Tooltips).
- **Tipagem Estrita em TypeScript:** Criar tipos e interfaces completos para todas as chamadas e eventos da bridge PyWebView.
- **Gerenciamento de Estado Reativo:** Usar Zustand ou React Context para o estado do pipeline, logs e seleção de projetos.
- **Experiência de Player Aprimorada:** Player de vídeo moderno com controle de velocidade, atalhos de teclado (espaço para pausar, setas para pular) e preview quadro a quadro.
- **Feedback Visual Avançado:** Toasts informativos via Sonner, skeletons durante carregamento de informações do YouTube e animações fluidas via Tailwind / Framer Motion.
