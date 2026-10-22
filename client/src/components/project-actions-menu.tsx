import {
    DotsThreeVertical,
    FolderOpen,
    Sparkle,
    Trash,
} from "@phosphor-icons/react"

import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface ProjectActionsMenuProps {
    isGeneratingThumbnails: boolean
    hasClips: boolean
    onGenerateAllThumbnails: () => void
    onOpenFolder: () => void
    onDeleteProject: () => void
}

export function ProjectActionsMenu({
    isGeneratingThumbnails,
    hasClips,
    onGenerateAllThumbnails,
    onOpenFolder,
    onDeleteProject,
}: ProjectActionsMenuProps) {
    return (
        <DropdownMenu>
            <DropdownMenuTrigger
                render={
                    <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        title="Mais ações do projeto"
                    />
                }
            >
                <DotsThreeVertical className="w-4 h-4" weight="bold" />
                <span>Mais ações</span>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem
                    disabled={isGeneratingThumbnails || !hasClips}
                    onClick={onGenerateAllThumbnails}
                >
                    <Sparkle
                        className={isGeneratingThumbnails ? "animate-spin" : ""}
                    />
                    <span>
                        {isGeneratingThumbnails
                            ? "Gerando thumbnails..."
                            : "Gerar todas as thumbnails (IA)"}
                    </span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onOpenFolder}>
                    <FolderOpen />
                    <span>Abrir pasta do projeto</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                    variant="destructive"
                    onClick={onDeleteProject}
                >
                    <Trash />
                    <span>Excluir projeto...</span>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
