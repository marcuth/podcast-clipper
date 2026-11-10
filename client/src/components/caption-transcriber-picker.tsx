import type { CaptionTranscriber } from "@/types/api"

interface CaptionTranscriberOption {
    value: CaptionTranscriber
    label: string
    description: string
}

const OPTIONS: CaptionTranscriberOption[] = [
    {
        value: "whisper",
        label: "Whisper local",
        description: "Grátis e offline, mais lento (CPU)",
    },
    {
        value: "assemblyai",
        label: "AssemblyAI Cloud",
        description: "Rápido, requer chave de API",
    },
]

interface CaptionTranscriberPickerProps {
    value: CaptionTranscriber
    onChange: (provider: CaptionTranscriber) => void
    disabled?: boolean
}

export function CaptionTranscriberPicker({
    value,
    onChange,
    disabled = false,
}: CaptionTranscriberPickerProps) {
    return (
        <div
            role="radiogroup"
            aria-label="Provedor de transcrição das legendas"
            className="grid grid-cols-1 gap-2 sm:grid-cols-2"
        >
            {OPTIONS.map((option) => {
                const selected = value === option.value

                return (
                    <button
                        key={option.value}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        disabled={disabled}
                        onClick={() => onChange(option.value)}
                        className={`rounded-lg border px-3 py-2 text-left transition-all outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50 ${
                            selected
                                ? "border-primary bg-primary/10 shadow-xs"
                                : "border-border/40 bg-muted/20 hover:border-border"
                        }`}
                    >
                        <span className="block text-xs font-bold text-foreground">
                            {option.label}
                        </span>
                        <span className="block text-[11px] text-muted-foreground">
                            {option.description}
                        </span>
                    </button>
                )
            })}
        </div>
    )
}
