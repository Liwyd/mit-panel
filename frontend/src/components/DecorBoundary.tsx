import { Component, type ReactNode } from 'react'

/**
 * Wraps purely decorative pieces (the Black Friday dust and countdown). If one
 * of them throws, it disappears instead of taking the page down with it; the
 * panel itself must never depend on decoration.
 */
export class DecorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
    state = { failed: false }

    static getDerivedStateFromError() {
        return { failed: true }
    }

    componentDidCatch(error: unknown) {
        console.error('Decoration failed and was hidden:', error)
    }

    render() {
        return this.state.failed ? null : this.props.children
    }
}
