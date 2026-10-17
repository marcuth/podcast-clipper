/**
 * Custom ESLint plugin to automatically detect and remove code comments.
 * Preserves essential directives like eslint-*, @ts-*, vite-*, and /// <reference>.
 */

export const removeCommentsRule = {
    meta: {
        type: "layout",
        fixable: "code",
        docs: {
            description: "Automatically remove code comments during lint --fix",
        },
        messages: {
            noComment: "Comments should be removed from code.",
        },
        schema: [],
    },
    create(context) {
        const sourceCode = context.sourceCode

        const shouldPreserve = (commentText) => {
            const trimmed = commentText.trim()
            return (
                trimmed.startsWith("eslint") ||
                trimmed.startsWith("@ts-") ||
                trimmed.startsWith("vite-") ||
                trimmed.startsWith("@vite-") ||
                trimmed.startsWith("///")
            )
        }

        return {
            // Handle JSX comment containers like {/* comment */}
            JSXEmptyExpression(node) {
                const comments = sourceCode.getCommentsInside(node)
                if (
                    comments.length > 0 &&
                    node.parent &&
                    node.parent.type === "JSXExpressionContainer"
                ) {
                    if (comments.some((c) => shouldPreserve(c.value))) {
                        return
                    }

                    const container = node.parent
                    context.report({
                        node: container,
                        messageId: "noComment",
                        fix(fixer) {
                            const text = sourceCode.text
                            let [start, end] = container.range
                            const lineStart =
                                text.lastIndexOf("\n", start - 1) + 1
                            const before = text.slice(lineStart, start)

                            // If only whitespace precedes the JSX container on this line
                            if (/^\s*$/.test(before)) {
                                start = lineStart
                                if (
                                    text[end] === "\r" &&
                                    text[end + 1] === "\n"
                                ) {
                                    end += 2
                                } else if (text[end] === "\n") {
                                    end += 1
                                }
                            }
                            return fixer.removeRange([start, end])
                        },
                    })
                }
            },

            // Handle standard // line comments and /* */ block comments
            Program() {
                const comments = sourceCode.getAllComments()
                for (const comment of comments) {
                    if (shouldPreserve(comment.value)) {
                        continue
                    }

                    // Skip comments inside JSXEmptyExpression handled above
                    try {
                        const node = sourceCode.getNodeByRangeIndex(
                            comment.range[0],
                        )
                        if (
                            node &&
                            (node.type === "JSXEmptyExpression" ||
                                (node.parent &&
                                    node.parent.type === "JSXEmptyExpression"))
                        ) {
                            continue
                        }
                    } catch {
                        // fallback to processing comment
                    }

                    context.report({
                        loc: comment.loc,
                        messageId: "noComment",
                        fix(fixer) {
                            const text = sourceCode.text
                            let [start, end] = comment.range
                            const lineStart =
                                text.lastIndexOf("\n", start - 1) + 1
                            const before = text.slice(lineStart, start)

                            // If comment is on its own line
                            if (/^\s*$/.test(before)) {
                                start = lineStart
                                if (
                                    text[end] === "\r" &&
                                    text[end + 1] === "\n"
                                ) {
                                    end += 2
                                } else if (text[end] === "\n") {
                                    end += 1
                                }
                            } else {
                                // If inline after code, trim single preceding space
                                if (
                                    start > 0 &&
                                    (text[start - 1] === " " ||
                                        text[start - 1] === "\t")
                                ) {
                                    start -= 1
                                }
                            }

                            return fixer.removeRange([start, end])
                        },
                    })
                }
            },
        }
    },
}

export default {
    rules: {
        "no-comments": removeCommentsRule,
    },
}
