import {
    ArrowsClockwise,
    ClosedCaptioning,
    Copy,
    DotsThreeVertical,
    FolderOpen,
    Play,
    Sparkle,
} from "@phosphor-icons/react"

import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuGroup,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { ClipItem } from "@/types/api"

interface ClipActionsMenuProps {
    clip: ClipItem
    isGeneratingThumbnail: boolean
    onGenerateThumbnail: () => void
    onRerender: () => void
    onApplySubtitles: () => void
    onOpenExternalPlayer: () => void
    onOpenThumbnailFile: () => void
    onCopyMetadata: () => void
}

export function ClipActionsMenu({
    clip,
    isGeneratingThumbnail,
    onGenerateThumbnail,
    onRerender,
    onApplySubtitles,
    onOpenExternalPlayer,
    onOpenThumbnailFile,
    onCopyMetadata,
}: ClipActionsMenuProps) {
    return (
        <DropdownMenu>
            <DropdownMenuTrigger
                render={
                    <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Ações do corte"
                        aria-label={`Ações de ${clip.name}`}
                    />
                }
            >
                <DotsThreeVertical className="w-4 h-4" weight="bold" />
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-60">
                <DropdownMenuGroup>
                    <DropdownMenuLabel>Vídeo</DropdownMenuLabel>
                    {clip.rendered && clip.format !== "long" && (
                        <DropdownMenuItem onClick={onApplySubtitles}>
                            <ClosedCaptioning />
                            <span>Aplicar legendas</span>
                        </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={onRerender}>
                        <ArrowsClockwise />
                        <span>
                            {clip.rendered
                                ? "Re-renderizar / Overlay"
                                : "Renderizar vídeo"}
                        </span>
                    </DropdownMenuItem>
                    {clip.rendered && clip.video_path && (
                        <DropdownMenuItem onClick={onOpenExternalPlayer}>
                            <Play />
                            <span>Abrir no player externo</span>
                        </DropdownMenuItem>
                    )}
                </DropdownMenuGroup>

                <DropdownMenuSeparator />

                <DropdownMenuGroup>
                    <DropdownMenuLabel>Thumbnail</DropdownMenuLabel>
                    <DropdownMenuItem
                        disabled={isGeneratingThumbnail}
                        onClick={onGenerateThumbnail}
                    >
                        <Sparkle
                            className={
                                isGeneratingThumbnail ? "animate-spin" : ""
                            }
                        />
                        <span>
                            {clip.thumbnail_url
                                ? "Regenerar thumbnail com IA"
                                : "Gerar thumbnail com IA"}
                        </span>
                    </DropdownMenuItem>
                    {clip.thumbnail_path && (
                        <DropdownMenuItem onClick={onOpenThumbnailFile}>
                            <FolderOpen />
                            <span>Ver arquivo da thumbnail</span>
                        </DropdownMenuItem>
                    )}
                </DropdownMenuGroup>

                <DropdownMenuSeparator />

                <DropdownMenuItem onClick={onCopyMetadata}>
                    <Copy />
                    <span>Copiar metadados</span>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
