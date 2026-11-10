# Interface de Linha de Comando (CLI)

O CLI executa todo o pipeline direto do terminal, sem abrir a interface desktop. O código fica em `src/cli/` (`args.py`, `wizard.py`, `observer.py`, `app.py`); `src/main.py` é só o ponto de entrada.

```bash
poetry run start                       # assistente interativo completo
poetry run start URL                   # pergunta só o que faltar
poetry run start URL --yes             # sem perguntas: usa flags e padrões
poetry run start URL -y --format long --max-clips 3
```

---

## 1. Flags

Tudo que for passado por flag **não é perguntado**. Com `--yes`, o que faltar usa o padrão.

| Flag | Valores | Efeito |
|---|---|---|
| `URL` | link do YouTube | vídeo a processar |
| `-y`, `--yes` | | não perguntar nada, não pedir confirmação |
| `--strategy` | `ai`, `heuristics` | como selecionar os cortes |
| `--transcription` | `assemblyai`, `whisper`, `yt_full`, `yt_partial` | origem da transcrição |
| `--format` | `short`, `long`, `timestamps` | 9:16, 16:9 ou só metadados |
| `--max-clips` | 1 a 15 | quantidade máxima de cortes |
| `--caption-style` | `remotion`, `ass` | estilo das legendas |
| `--caption-provider` | `whisper`, `assemblyai` | quem sincroniza as palavras das legendas |
| `--no-subtitles` / `--no-vignette` / `--no-split-screen` / `--no-heatmap` | | desliga cada recurso |
| `--keep-video` | | mantém o vídeo original baixado |
| `-v`, `--verbose` | | logs detalhados das bibliotecas |

Padrões inteligentes: a seleção e a transcrição padrão dependem das chaves configuradas. Sem `GEMINI_API_KEY` o padrão é heurísticas; sem `ASSEMBLY_AI_API_KEY` o padrão é as legendas do YouTube.

---

## 2. Assistente interativo

Perguntas, na ordem (cada uma só aparece se fizer sentido):

1. URL do vídeo (validada na hora; erro de digitação não derruba o assistente).
2. Estratégia de seleção dos cortes (IA ou heurísticas) e, para heurísticas, uso do heatmap.
3. Origem da transcrição. Opções sem chave configurada aparecem marcadas.
4. Formato: shorts 9:16, cortes longos 16:9 ou só timestamps.
5. Shorts: legendas, estilo, provedor de sincronização (Whisper local ou AssemblyAI), vinheta, split-screen.
   Longos: remoção de silêncio e overlay (com opção de salvar como padrão no `.env`).
6. Quantidade máxima de cortes (1 a 15, validada).
7. Resumo das escolhas e confirmação para iniciar.

`Ctrl+C` ou `Esc` em qualquer pergunta cancela com segurança (código de saída 130).

---

## 3. Durante a execução

- Barra de progresso com etapa, porcentagem e tempo decorrido; avisos e erros aparecem em cores acima da barra.
- Cada corte pronto é listado na hora (`+ short_01 01:00 -> 01:45 (45s) Título`).
- Antes de começar, o CLI avisa o que vai mudar o resultado: chave do Gemini ou da AssemblyAI ausente (cai para heurísticas/Whisper), FFmpeg ou Node fora do PATH.
- `Ctrl+C` uma vez cancela ao fim da etapa atual; uma segunda vez encerra imediatamente.
- No fim: tabela com os cortes gerados e a pasta de saída (`output/<slug>/`).

### Códigos de saída

| Código | Significado |
|---|---|
| 0 | concluído |
| 1 | erro (URL inválida, falha no pipeline) |
| 130 | cancelado pelo usuário |

Os resultados podem ser abertos depois na aba **Biblioteca** da interface gráfica (`poetry run gui`).
