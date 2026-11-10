interface LogoProps {
    size?: number
    className?: string
}

export function Logo({ size = 40, className = "" }: LogoProps) {
    return (
        <img
            src={`${import.meta.env.BASE_URL}logo.svg`}
            alt="Podcast Clipper"
            width={size}
            height={size}
            draggable={false}
            className={`shrink-0 rounded-xl shadow-md shadow-primary/25 ${className}`}
        />
    )
}
