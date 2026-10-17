import {
    ArrowsClockwise,
    ChatTeardropText,
    CheckCircle,
    Cpu,
    FloppyDisk,
    FolderOpen,
    Image,
    Info,
    Key,
    Lightning,
    Scissors,
    ShieldCheck,
    Sparkle,
    WarningCircle,
    Waveform,
    XCircle,
} from "@phosphor-icons/react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { getClipperBridge } from "@/lib/bridge"
import type { SystemInfo } from "@/types/api"

const AVAILABLE_GEMINI_MODELS = [
    {
        id: "gemini-2.5-flash",
        name: "Gemini 2.5 Flash",
        description:
            "Recomendado: Máxima velocidade e raciocínio multimodal moderno.",
    },
    {
        id: "gemini-2.0-flash",
        name: "Gemini 2.0 Flash",
        description: "Equilibrado: Alta performance e precisão de metadados.",
    },
    {
        id: "gemini-1.5-flash",
        name: "Gemini 1.5 Flash",
        description: "Versão clássica estável para títulos e hashtags.",
    },
]

export function DiagnosticTab() {
    const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
    const [isLoading, setIsLoading] = useState<boolean>(true)
    const [apiKeyInput, setApiKeyInput] = useState<string>("")
    const [selectedModel, setSelectedModel] =
        useState<string>("gemini-2.5-flash")
    const [isSavingKey, setIsSavingKey] = useState<boolean>(false)
    const [isSavingModel, setIsSavingModel] = useState<boolean>(false)
    const [overlayInput, setOverlayInput] = useState<string>("")
    const [isSavingOverlay, setIsSavingOverlay] = useState<boolean>(false)

    const fetchSystemDiagnostics = useCallback(async () => {
        setIsLoading(true)
        const bridge = getClipperBridge()
        if (!bridge) {
            setIsLoading(false)
            return
        }

        try {
            const diagnostics = await bridge.get_system_info()
            if (diagnostics) {
                setSystemInfo(diagnostics)
                if (diagnostics.gemini_model) {
                    setSelectedModel(diagnostics.gemini_model)
                }
                if (diagnostics.default_long_clip_overlay) {
                    setOverlayInput(diagnostics.default_long_clip_overlay)
                }
            }
        } catch (error) {
            console.error("Falha ao obter diagnósticos do sistema:", error)
            toast.error("Não foi possível carregar as informações do sistema.")
        } finally {
            setIsLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchSystemDiagnostics()
    }, [fetchSystemDiagnostics])

    const handleSaveApiKey = async () => {
        const bridge = getClipperBridge()
        if (!bridge) return

        const cleanedKey = apiKeyInput.trim()
        if (!cleanedKey) {
            toast.error("Por favor, digite uma chave de API válida.")
            return
        }

        setIsSavingKey(true)
        try {
            const response = await bridge.save_gemini_api_key(cleanedKey)
            if (response.success) {
                toast.success(
                    response.message ||
                        "Chave Gemini atualizada com sucesso no .env!",
                )
                setApiKeyInput("")
                fetchSystemDiagnostics()
            } else {
                toast.error(response.error || "Erro ao salvar chave.")
            }
        } catch {
            toast.error("Falha ao se comunicar com o backend.")
        } finally {
            setIsSavingKey(false)
        }
    }

    const handleSaveModel = async () => {
        const bridge = getClipperBridge()
        if (!bridge) return

        setIsSavingModel(true)
        try {
            const response = await bridge.save_gemini_model(selectedModel)
            if (response.success) {
                toast.success(
                    response.message || "Modelo Gemini salvo com sucesso!",
                )
                fetchSystemDiagnostics()
            } else {
                toast.error(response.error || "Erro ao salvar modelo.")
            }
        } catch {
            toast.error("Falha ao se comunicar com o backend.")
        } finally {
            setIsSavingModel(false)
        }
    }

    const handleSelectOverlayFile = async () => {
        const bridge = getClipperBridge()
        if (!bridge) return

        try {
            const result = await bridge.select_overlay_file()
            if (result.success && result.file_path) {
                setOverlayInput(result.file_path)
                toast.success("Arquivo de overlay selecionado!")
            } else if (result.error) {
                toast.error(result.error)
            }
        } catch (error) {
            toast.error(`Erro ao abrir seletor: ${String(error)}`)
        }
    }

    const handleSaveDefaultOverlay = async () => {
        const bridge = getClipperBridge()
        if (!bridge) return

        const cleanedPath = overlayInput.trim()
        setIsSavingOverlay(true)
        try {
            const response =
                await bridge.save_default_long_clip_overlay(cleanedPath)
            if (response.success) {
                toast.success(
                    response.message ||
                        "Overlay padrão atualizado com sucesso no .env!",
                )
                fetchSystemDiagnostics()
            } else {
                toast.error(response.error || "Erro ao salvar overlay padrão.")
            }
        } catch {
            toast.error("Falha ao se comunicar com o backend.")
        } finally {
            setIsSavingOverlay(false)
        }
    }

    const handleOpenFolder = async (folderPath: string) => {
        const bridge = getClipperBridge()
        if (!bridge || !folderPath) return

        try {
            await bridge.open_folder(folderPath)
            toast.success("Pasta aberta no Explorador de Arquivos")
        } catch {
            toast.error("Erro ao abrir pasta")
        }
    }

    return (
        <div className="flex flex-col gap-8 pb-10">
            {/* System Info & AI Config Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* AI Configuration */}
                <Card className="border-border/60 bg-card/40 backdrop-blur-md">
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Sparkle className="w-5 h-5 text-primary" />
                                <CardTitle className="text-base font-semibold">
                                    Google Gemini AI
                                </CardTitle>
                            </div>

                            {isLoading ? (
                                <Skeleton className="h-5 w-20" />
                            ) : systemInfo?.gemini_configured ? (
                                <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 gap-1 text-xs">
                                    <CheckCircle className="w-3.5 h-3.5" />
                                    <span>Configurada</span>
                                </Badge>
                            ) : (
                                <Badge
                                    variant="outline"
                                    className="border-amber-500/40 text-amber-400 bg-amber-500/10 gap-1 text-xs"
                                >
                                    <WarningCircle className="w-3.5 h-3.5" />
                                    <span>Não encontrada</span>
                                </Badge>
                            )}
                        </div>
                        <CardDescription className="text-xs">
                            Utilizada para sumarização viral, seleção
                            inteligente de cortes e metadados SEO.
                        </CardDescription>
                    </CardHeader>

                    <CardContent className="flex flex-col gap-5">
                        {/* API Key Section */}
                        <div className="flex flex-col gap-2">
                            <Label className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
                                <span className="flex items-center gap-1.5">
                                    <Key className="w-3.5 h-3.5" />
                                    <span>Chave de API (GEMINI_API_KEY)</span>
                                </span>
                                {systemInfo?.gemini_key_preview && (
                                    <span className="font-mono text-[11px] text-muted-foreground">
                                        Atual: {systemInfo.gemini_key_preview}
                                    </span>
                                )}
                            </Label>
                            <div className="flex gap-2">
                                <Input
                                    type="password"
                                    value={apiKeyInput}
                                    onChange={(event) =>
                                        setApiKeyInput(event.target.value)
                                    }
                                    placeholder={
                                        systemInfo?.gemini_configured
                                            ? "Digitar nova chave para substituir..."
                                            : "Cole sua chave AI Studio aqui..."
                                    }
                                    className="text-xs font-mono bg-background/50 flex-1"
                                />
                                <Button
                                    size="sm"
                                    onClick={handleSaveApiKey}
                                    disabled={
                                        isSavingKey || !apiKeyInput.trim()
                                    }
                                    className="gap-1.5 text-xs shrink-0"
                                >
                                    <FloppyDisk className="w-3.5 h-3.5" />
                                    <span>
                                        {isSavingKey ? "Salvando..." : "Salvar"}
                                    </span>
                                </Button>
                            </div>
                            <span className="text-[11px] text-muted-foreground">
                                A chave é gravada com segurança no seu arquivo
                                local{" "}
                                <code className="bg-muted px-1 py-0.5 rounded text-foreground">
                                    .env
                                </code>
                                .
                            </span>
                        </div>

                        {/* Model Selection */}
                        <div className="flex flex-col gap-2 pt-2 border-t border-border/40">
                            <Label className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                                <Cpu className="w-3.5 h-3.5" />
                                <span>Modelo Gemini Selecionado</span>
                            </Label>

                            <div className="grid grid-cols-1 gap-2">
                                {AVAILABLE_GEMINI_MODELS.map((modelItem) => (
                                    <button
                                        type="button"
                                        key={modelItem.id}
                                        onClick={() =>
                                            setSelectedModel(modelItem.id)
                                        }
                                        className={`flex flex-col text-left p-3 rounded-lg border text-xs transition ${
                                            selectedModel === modelItem.id
                                                ? "border-primary bg-primary/10 text-foreground"
                                                : "border-border/60 bg-muted/10 text-muted-foreground hover:border-border hover:bg-muted/20"
                                        }`}
                                    >
                                        <div className="flex items-center justify-between font-semibold text-foreground mb-0.5">
                                            <span>{modelItem.name}</span>
                                            {selectedModel === modelItem.id && (
                                                <Badge
                                                    variant="secondary"
                                                    className="text-[10px] px-1.5 py-0 h-4 bg-primary/20 text-primary border-primary/30"
                                                >
                                                    Ativo
                                                </Badge>
                                            )}
                                        </div>
                                        <span className="text-[11px] text-muted-foreground">
                                            {modelItem.description}
                                        </span>
                                    </button>
                                ))}
                            </div>

                            <div className="flex justify-end pt-1">
                                <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={handleSaveModel}
                                    disabled={
                                        isSavingModel ||
                                        selectedModel ===
                                            systemInfo?.gemini_model
                                    }
                                    className="gap-1.5 text-xs"
                                >
                                    <FloppyDisk className="w-3.5 h-3.5" />
                                    <span>
                                        {isSavingModel
                                            ? "Salvando..."
                                            : selectedModel ===
                                                systemInfo?.gemini_model
                                              ? "Modelo já em uso"
                                              : "Definir como Modelo Padrão"}
                                    </span>
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Local Environment & Models */}
                <Card className="border-border/60 bg-card/40 backdrop-blur-md">
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Cpu className="w-5 h-5 text-primary" />
                                <CardTitle className="text-base font-semibold">
                                    Ambiente & Modelos Locais
                                </CardTitle>
                            </div>

                            <Button
                                variant="outline"
                                size="icon"
                                onClick={fetchSystemDiagnostics}
                                disabled={isLoading}
                                className="h-7 w-7"
                                title="Recarregar diagnósticos"
                            >
                                <ArrowsClockwise
                                    className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`}
                                />
                            </Button>
                        </div>
                        <CardDescription className="text-xs">
                            Recursos de visão computacional, face-tracking e
                            diretórios do pipeline.
                        </CardDescription>
                    </CardHeader>

                    <CardContent className="flex flex-col gap-4 text-xs">
                        {/* Status items */}
                        <div className="space-y-3">
                            <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/20 border border-border/40">
                                <div className="flex flex-col">
                                    <span className="font-semibold text-foreground">
                                        MediaPipe BlazeFace (Tracking de Rosto)
                                    </span>
                                    <span className="text-[11px] text-muted-foreground">
                                        Modelo leve em{" "}
                                        <code className="bg-muted px-1 rounded">
                                            models/blaze_face_short_range.tflite
                                        </code>
                                    </span>
                                </div>
                                {isLoading ? (
                                    <Skeleton className="h-5 w-20" />
                                ) : systemInfo?.face_model_available ? (
                                    <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 gap-1 text-[11px]">
                                        <CheckCircle className="w-3.5 h-3.5" />
                                        <span>Instalado</span>
                                    </Badge>
                                ) : (
                                    <Badge
                                        variant="destructive"
                                        className="gap-1 text-[11px]"
                                    >
                                        <XCircle className="w-3.5 h-3.5" />
                                        <span>Ausente</span>
                                    </Badge>
                                )}
                            </div>

                            <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/20 border border-border/40">
                                <span className="font-semibold text-foreground">
                                    Python Runtime
                                </span>
                                <span className="font-mono text-muted-foreground">
                                    {systemInfo?.python_version ||
                                        "Carregando..."}
                                </span>
                            </div>

                            <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/20 border border-border/40">
                                <span className="font-semibold text-foreground">
                                    Sistema Operacional
                                </span>
                                <span className="text-muted-foreground">
                                    {systemInfo?.os || "Windows 10"}
                                </span>
                            </div>

                            <div className="flex flex-col gap-2 p-2.5 rounded-lg bg-muted/20 border border-border/40">
                                <div className="flex items-center justify-between">
                                    <span className="font-semibold text-foreground">
                                        Diretório de Saída (output/)
                                    </span>
                                    {systemInfo?.output_dir && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() =>
                                                handleOpenFolder(
                                                    systemInfo.output_dir,
                                                )
                                            }
                                            className="h-6 text-[11px] gap-1 px-2 text-primary hover:text-primary"
                                        >
                                            <FolderOpen className="w-3 h-3" />
                                            <span>Abrir Pasta</span>
                                        </Button>
                                    )}
                                </div>
                                <span className="font-mono text-[11px] text-muted-foreground truncate">
                                    {systemInfo?.output_dir || "output/"}
                                </span>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Overlay Padrão para Cortes Longos (16:9) */}
            <Card className="border-border/60 bg-card/40 backdrop-blur-md">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Image
                                className="w-5 h-5 text-primary"
                                weight="bold"
                            />
                            <CardTitle className="text-base font-semibold">
                                Moldura / Overlay Padrão para Cortes Longos
                                (16:9)
                            </CardTitle>
                        </div>

                        {systemInfo?.has_default_overlay ? (
                            <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 gap-1 text-xs">
                                <CheckCircle className="w-3.5 h-3.5" />
                                <span>Configurado</span>
                            </Badge>
                        ) : (
                            <Badge
                                variant="outline"
                                className="border-border/60 text-muted-foreground gap-1 text-xs"
                            >
                                <span>Opcional (Não definido)</span>
                            </Badge>
                        )}
                    </div>
                    <CardDescription className="text-xs">
                        Define uma imagem de moldura artística ou watermark
                        padrão gravada em{" "}
                        <code className="bg-muted px-1 py-0.5 rounded text-foreground font-mono">
                            .env
                        </code>{" "}
                        para aplicar automaticamente em todos os cortes de
                        podcasts panorâmicos.
                    </CardDescription>
                </CardHeader>

                <CardContent className="flex flex-col gap-4">
                    <div className="flex flex-col gap-2">
                        <Label className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
                            <span>
                                Caminho do arquivo de imagem (PNG ou JPG)
                            </span>
                            {systemInfo?.default_long_clip_overlay && (
                                <span className="font-mono text-[11px] text-muted-foreground truncate max-w-xs">
                                    Ativo:{" "}
                                    {systemInfo.default_long_clip_overlay}
                                </span>
                            )}
                        </Label>
                        <div className="flex flex-col gap-2 sm:flex-row">
                            <Input
                                value={overlayInput}
                                onChange={(event) =>
                                    setOverlayInput(event.target.value)
                                }
                                placeholder="Ex: assets/overlays/frame.png ou D:\...\moldura.png"
                                className="text-xs font-mono bg-background/50 flex-1"
                            />
                            <div className="flex items-center gap-2 shrink-0">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleSelectOverlayFile}
                                    className="gap-1.5 text-xs font-semibold"
                                >
                                    <FolderOpen className="w-3.5 h-3.5" />
                                    <span>Procurar...</span>
                                </Button>
                                <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={handleSaveDefaultOverlay}
                                    disabled={
                                        isSavingOverlay ||
                                        overlayInput.trim() ===
                                            (systemInfo?.default_long_clip_overlay ||
                                                "")
                                    }
                                    className="gap-1.5 text-xs font-semibold"
                                >
                                    <FloppyDisk className="w-3.5 h-3.5" />
                                    <span>
                                        {isSavingOverlay
                                            ? "Salvando..."
                                            : overlayInput.trim() ===
                                                (systemInfo?.default_long_clip_overlay ||
                                                    "")
                                              ? "Salvo no .env"
                                              : "Salvar como Padrão"}
                                    </span>
                                </Button>
                            </div>
                        </div>
                        <span className="text-[11px] text-muted-foreground leading-relaxed">
                            O FFmpeg redimensionará a imagem automaticamente
                            para se ajustar exatamente à resolução do vídeo
                            mantendo a proporção 16:9. Para desativar o padrão,
                            deixe o campo em branco e clique em Salvar.
                        </span>
                    </div>
                </CardContent>
            </Card>

            {/* Viral Heuristics Reference Guide Section */}
            <Card className="border-border/60 bg-card/30 backdrop-blur-md">
                <CardHeader>
                    <div className="flex items-center gap-2">
                        <Lightning className="w-5 h-5 text-amber-400" />
                        <CardTitle className="text-base font-semibold">
                            Manual de Heurísticas Virais & Regras de Extração
                        </CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Baseado na metodologia de destaque de podcasts: sinais
                        fracos combinados para detectar momentos de alto impacto
                        e retenção.
                    </CardDescription>
                </CardHeader>

                <CardContent className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {/* Heuristic 1: Attention Triggers */}
                    <div className="p-4 rounded-xl bg-muted/15 border border-border/40 flex flex-col gap-2.5">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                                <ChatTeardropText className="w-4 h-4 text-primary" />
                                <span>Gatilhos de Atenção</span>
                            </span>
                            <Badge
                                variant="outline"
                                className="text-[10px] text-emerald-400 border-emerald-500/30"
                            >
                                +0.5 a +1.0 pts
                            </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                            Expressões que despertam o cérebro humano para
                            escuta ativa:
                        </p>
                        <div className="flex flex-wrap gap-1">
                            {[
                                "presta atenção",
                                "olha só",
                                "o ponto é",
                                "o problema é",
                                "o segredo é",
                                "isso muda tudo",
                            ].map((triggerPhrase) => (
                                <span
                                    key={triggerPhrase}
                                    className="px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-mono"
                                >
                                    "{triggerPhrase}"
                                </span>
                            ))}
                        </div>
                    </div>

                    {/* Heuristic 2: Contrast & Twist */}
                    <div className="p-4 rounded-xl bg-muted/15 border border-border/40 flex flex-col gap-2.5">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                                <Sparkle className="w-4 h-4 text-purple-400" />
                                <span>Contraste & Virada Semântica</span>
                            </span>
                            <Badge
                                variant="outline"
                                className="text-[10px] text-purple-400 border-purple-500/30"
                            >
                                +0.7 pts
                            </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                            Mudanças de perspectiva geram quebra de expectativa
                            no ouvinte:
                        </p>
                        <ul className="text-[11px] text-muted-foreground space-y-1 list-disc list-inside">
                            <li>
                                <em className="text-foreground">
                                    "antes eu pensava X, hoje penso Y"
                                </em>
                            </li>
                            <li>
                                <em className="text-foreground">
                                    "todo mundo acha..., mas..."
                                </em>
                            </li>
                            <li>
                                <em className="text-foreground">
                                    "parecia certo, mas na prática..."
                                </em>
                            </li>
                        </ul>
                    </div>

                    {/* Heuristic 3: Tweetable Sentences */}
                    <div className="p-4 rounded-xl bg-muted/15 border border-border/40 flex flex-col gap-2.5">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                                <Info className="w-4 h-4 text-cyan-400" />
                                <span>Frases Tweetáveis</span>
                            </span>
                            <Badge
                                variant="outline"
                                className="text-[10px] text-cyan-400 border-cyan-500/30"
                            >
                                +0.3 pts
                            </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                            Frases curtas (8 a 20 palavras), assertivas e
                            conclusivas com alta densidade de sabedoria:
                        </p>
                        <div className="p-2 rounded bg-muted/30 border border-border/40 text-[11px] italic text-foreground/90">
                            "Disciplina é escolher entre o que você quer agora e
                            o que você mais quer."
                        </div>
                    </div>

                    {/* Heuristic 4: Temporal & Dramatic Pause */}
                    <div className="p-4 rounded-xl bg-muted/15 border border-border/40 flex flex-col gap-2.5">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                                <Scissors className="w-4 h-4 text-amber-400" />
                                <span>Pausa Dramática & Ritmo</span>
                            </span>
                            <Badge
                                variant="outline"
                                className="text-[10px] text-amber-400 border-amber-500/30"
                            >
                                +0.2 a +0.4 pts
                            </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                            Momentos fortes vêm após uma pausa respiratória
                            curta (&gt; 0.4s) seguida de aceleração e
                            continuidade de 3 segmentos fortes contíguos.
                        </p>
                    </div>

                    {/* Heuristic 5: Audio Energy & Volume */}
                    <div className="p-4 rounded-xl bg-muted/15 border border-border/40 flex flex-col gap-2.5">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                                <Waveform className="w-4 h-4 text-emerald-400" />
                                <span>Energia Vocal (RMS)</span>
                            </span>
                            <Badge
                                variant="outline"
                                className="text-[10px] text-emerald-400 border-emerald-500/30"
                            >
                                +0.4 a +0.5 pts
                            </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                            Momentos emotivos ou de empolgação provocam picos de
                            energia sonora (&gt; 1.3x da média) e maior
                            densidade de palavras por segundo.
                        </p>
                    </div>

                    {/* Heuristic 6: Anti-heuristics & Safe Margin */}
                    <div className="p-4 rounded-xl bg-muted/15 border border-border/40 flex flex-col gap-2.5">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                                <ShieldCheck className="w-4 h-4 text-rose-400" />
                                <span>Anti-Heurísticas & Margem</span>
                            </span>
                            <Badge
                                variant="outline"
                                className="text-[10px] text-rose-400 border-rose-500/30"
                            >
                                -0.5 pts
                            </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                            Filtra frases vazias, prolixas (&gt; 30 palavras) e
                            gaguejos ("ééé", "tipo"). Aplica corte de segurança:{" "}
                            <strong>
                                1-2s antes do gancho e 1-2s após a conclusão
                            </strong>
                            .
                        </p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
