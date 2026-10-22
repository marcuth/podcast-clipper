import { loadFont } from "@remotion/google-fonts/Poppins"
import { measureText } from "@remotion/layout-utils"
import { useEffect, useMemo, useState } from "react"
import { AbsoluteFill, continueRender, delayRender, spring, useCurrentFrame, useVideoConfig } from "remotion"

const { fontFamily, waitUntilDone } = loadFont("normal", { weights: ["800"], subsets: ["latin", "latin-ext"] })

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
const MAX_FONT_SIZE = 115
const MIN_PAIR_FONT_SIZE = 75
const FRAME_WIDTH = 1080
const SIDE_MARGIN = 40
const MEASURE_FONT_SIZE = 100
const GAP_EM = 0.4
const STROKE_EM = 0.09
// Active word pop (1.1) times the page spring overshoot, with some slack.
const ANIMATION_SAFETY = 1.15

type Page = {
    words: CaptionWord[]
    start: number
    end: number
}

const widthCache = new Map<string, number>()

const measureWord = (text: string): number => {
    const cached = widthCache.get(text)

    if (cached !== undefined) return cached

    const { width } = measureText({
        text: text.toUpperCase(),
        fontFamily,
        fontSize: MEASURE_FONT_SIZE,
        fontWeight: 800,
        validateFontIsLoaded: true,
    })

    widthCache.set(text, width)

    return width
}

const fitFontSize = (words: CaptionWord[]): number => {
    const wordsWidthEm = words.reduce((total, item) => total + measureWord(item.word), 0) / MEASURE_FONT_SIZE
    const totalEm = (wordsWidthEm + (words.length - 1) * GAP_EM + STROKE_EM) * ANIMATION_SAFETY

    return Math.min(MAX_FONT_SIZE, Math.floor((FRAME_WIDTH - 2 * SIDE_MARGIN) / totalEm))
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
        // Two wide words would force a tiny font: give each its own page instead.
        if (current.length > 0 && fitFontSize([...current, word]) < MIN_PAIR_FONT_SIZE) {
            flush()
        }

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

const useFontReady = (): boolean => {
    const [handle] = useState(() => delayRender("Loading Poppins"))
    const [ready, setReady] = useState(false)

    useEffect(() => {
        waitUntilDone().then(() => {
            setReady(true)
            continueRender(handle)
        })
    }, [handle])

    return ready
}

export const Captions = ({ words }: CaptionsProps) => {
    const frame = useCurrentFrame()
    const { fps } = useVideoConfig()
    const fontReady = useFontReady()
    const pages = useMemo(() => (fontReady ? buildPages(words) : []), [fontReady, words])
    const time = frame / fps

    const page = pages.find((item) => time >= item.start && time < item.end)

    if (!page) {
        return <AbsoluteFill />
    }

    const pageEntrance = spring({
        frame: frame - Math.round(page.start * fps),
        fps,
        config: { damping: 12, stiffness: 220, mass: 0.6 },
    })

    const fontSize = fitFontSize(page.words)

    return (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: BOTTOM_OFFSET }}>
            <div
                style={{
                    display: "flex",
                    gap: fontSize * GAP_EM,
                    transform: `scale(${0.6 + 0.4 * pageEntrance})`,
                    opacity: Math.min(1, pageEntrance * 2),
                    fontFamily,
                    fontWeight: 800,
                    fontSize,
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
                                WebkitTextStroke: `${Math.round(fontSize * STROKE_EM)}px #000`,
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
