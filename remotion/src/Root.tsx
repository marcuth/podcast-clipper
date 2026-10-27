import { Composition } from "remotion"

import { Captions, CaptionsProps } from "./Captions"

export const FPS = 30

const defaultProps: CaptionsProps = {
    words: [],
    durationInSeconds: 1,
    centerRanges: [],
}

export const Root = () => {
    return (
        <Composition
            id="Captions"
            component={Captions}
            width={1080}
            height={1920}
            fps={FPS}
            durationInFrames={FPS}
            defaultProps={defaultProps}
            calculateMetadata={({ props }) => ({
                durationInFrames: Math.max(1, Math.ceil(props.durationInSeconds * FPS)),
            })}
        />
    )
}
