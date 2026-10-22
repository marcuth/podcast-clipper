import { loadFont } from "@remotion/google-fonts/Poppins"
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion"

const { fontFamily } = loadFont("normal", { weights: ["800"], subsets: ["latin", "latin-ext"] })

export type CaptionWord = {
    word: string
    start: number
    end: number
}

export type CaptionsProps = {
    words: CaptionWord[]
    durationInSeconds: number
}

const MAX_WORDS_PER_PAGE = 2
const MAX_CHARS_PER_PAGE = 12
const ACTIVE_COLOR = "#FFE500"
const INACTIVE_COLOR = "#FFFFFF"
const BOTTOM_OFFSET = 650

type Page = {
    words: CaptionWord[]
    start: number
    end: number
}

const buildPages = (words: CaptionWord[]): Page[] => {
    const pages: Page[] = []
    let current: CaptionWord[] = []

    const flush = () => {
        if (current.length === 0) return

        pages.push({
            words: current,
            start: current[0].start,
            end: current[current.length - 1].end,
        })

        current = []
    }

    for (const word of words) {
        current.push(word)

        const length = current.map((item) => item.word).join(" ").length

        if (current.length >= MAX_WORDS_PER_PAGE || length > MAX_CHARS_PER_PAGE) {
            flush()
        }
    }

    flush()

    // Keep each page on screen until the next one starts so there is no flicker between pages.
    return pages.map((page, index) => {
        const next = pages[index + 1]
        const end = next ? Math.min(Math.max(page.end, next.start - 0.001), next.start) : page.end + 0.25
        return { ...page, end }
    })
}

export const Captions = ({ words }: CaptionsProps) => {
    const frame = useCurrentFrame()
    const { fps } = useVideoConfig()
    const time = frame / fps

    const page = buildPages(words).find((item) => time >= item.start && time < item.end)

    if (!page) {
        return <AbsoluteFill />
    }

    const pageEntrance = spring({
        frame: frame - Math.round(page.start * fps),
        fps,
        config: { damping: 12, stiffness: 220, mass: 0.6 },
    })

    return (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: BOTTOM_OFFSET }}>
            <div
                style={{
                    display: "flex",
                    gap: 48,
                    transform: `scale(${0.6 + 0.4 * pageEntrance})`,
                    opacity: Math.min(1, pageEntrance * 2),
                    fontFamily,
                    fontWeight: 800,
                    fontSize: 115,
                    textTransform: "uppercase",
                    textAlign: "center",
                    whiteSpace: "nowrap",
                }}
            >
                {page.words.map((word, index) => {
                    const isActive = time >= word.start && time < word.end
                    const wordPop = spring({
                        frame: frame - Math.round(word.start * fps),
                        fps,
                        config: { damping: 9, stiffness: 260, mass: 0.5 },
                    })

                    return (
                        <span
                            key={`${word.start}-${index}`}
                            style={{
                                color: isActive ? ACTIVE_COLOR : INACTIVE_COLOR,
                                transform: `scale(${isActive ? 1 + 0.1 * wordPop : 1})`,
                                WebkitTextStroke: "10px #000",
                                paintOrder: "stroke fill",
                                textShadow: "0 8px 24px rgba(0,0,0,0.5)",
                            }}
                        >
                            {word.word}
                        </span>
                    )
                })}
            </div>
        </AbsoluteFill>
    )
}
