"""Command-line flags. Anything left unset is asked interactively (or defaulted with ``--yes``)."""

import argparse

EXAMPLES = """\
exemplos:
  poetry run start                                   assistente interativo completo
  poetry run start URL                               pergunta só o resto
  poetry run start URL --yes                         usa os padrões, sem perguntas
  poetry run start URL -y --format long --max-clips 3
  poetry run start URL -y --strategy heuristics --transcription whisper
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="podcast-clipper",
        description="Gera cortes (shorts verticais ou cortes longos) a partir de um vídeo do YouTube.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="link do vídeo do YouTube")
    parser.add_argument("-y", "--yes", action="store_true", help="não perguntar nada: usa flags e padrões")
    parser.add_argument("--strategy", choices=["ai", "heuristics"], help="como selecionar os cortes")
    parser.add_argument(
        "--transcription",
        choices=["assemblyai", "whisper", "yt_full", "yt_partial"],
        help="de onde vem a transcrição",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["short", "long", "timestamps"],
        help="short = 9:16 com legendas, long = 16:9, timestamps = só metadados",
    )
    parser.add_argument("--max-clips", type=int, help="quantidade máxima de cortes (1 a 15)")
    parser.add_argument("--caption-style", choices=["remotion", "ass"], help="estilo das legendas")
    parser.add_argument(
        "--caption-provider",
        choices=["whisper", "assemblyai"],
        help="quem sincroniza as palavras das legendas",
    )
    parser.add_argument("--no-subtitles", action="store_true", help="não queimar legendas nos shorts")
    parser.add_argument("--no-vignette", action="store_true", help="sem efeito de vinheta")
    parser.add_argument("--no-split-screen", action="store_true", help="sem split-screen para 2 pessoas")
    parser.add_argument("--no-heatmap", action="store_true", help="não usar o heatmap do YouTube")
    parser.add_argument("--keep-video", action="store_true", help="manter o vídeo original baixado")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostrar logs detalhados das bibliotecas")
    return parser
