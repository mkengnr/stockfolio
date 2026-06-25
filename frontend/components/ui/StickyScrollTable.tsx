'use client'

import { useEffect, useRef } from 'react'

interface Props {
  children: React.ReactNode
  /** Offset from the top of the viewport where the floating header parks (navbar + sticky filter). */
  stickyTop?: number
  className?: string
}

/**
 * Renders a horizontally-scrollable table that flows in the page (vertical
 * scrolling is the window, not an inner scroll region). While the table
 * straddles the sticky line, a clone of its <thead> floats fixed at the top so
 * the column header stays visible until the table ends. The clone mirrors the
 * wrapper's horizontal scroll, preserving the sticky first column.
 */
export function StickyScrollTable({ children, stickyTop = 112, className = '' }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const floatRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const scroller = scrollRef.current
    const float = floatRef.current
    if (!scroller || !float) return
    const table = scroller.querySelector('table')
    const thead = table?.querySelector('thead')
    if (!table || !thead) return

    const theadEl = thead as HTMLElement

    function buildClone() {
      if (!float || !table || !thead) return
      float.innerHTML = ''
      const tableClone = table.cloneNode(false) as HTMLTableElement
      tableClone.style.width = `${table.offsetWidth}px`
      const theadClone = thead.cloneNode(true) as HTMLElement
      // The clone is the visible sticky header — keep it shown even while we hide the
      // in-flow <thead> below, and don't inherit that hidden state via cloneNode.
      theadClone.style.visibility = 'visible'
      tableClone.appendChild(theadClone)
      float.appendChild(tableClone)
    }

    function syncHorizontal() {
      if (float) float.scrollLeft = scroller!.scrollLeft
    }

    function update() {
      if (!scroller || !float) return
      const rect = scroller.getBoundingClientRect()
      const active = rect.top < stickyTop && rect.bottom > stickyTop + 28
      if (active) {
        if (!float.firstChild) buildClone()
        float.style.display = 'block'
        float.style.top = `${stickyTop}px`
        float.style.left = `${rect.left}px`
        float.style.width = `${rect.width}px`
        syncHorizontal()
        // Hide the in-flow header while the clone stands in for it. Otherwise the real
        // <thead>, still scrolling through the band between the page toolbar and the clone,
        // peeks out as a ghost duplicate of the floating header.
        theadEl.style.visibility = 'hidden'
      } else {
        float.style.display = 'none'
        theadEl.style.visibility = ''
      }
    }

    function rebuild() {
      if (float) float.innerHTML = ''
      update()
    }

    update()
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', rebuild)
    scroller.addEventListener('scroll', syncHorizontal, { passive: true })
    const observer = new MutationObserver(rebuild)
    observer.observe(table, { childList: true, subtree: true })

    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', rebuild)
      scroller.removeEventListener('scroll', syncHorizontal)
      observer.disconnect()
      theadEl.style.visibility = ''
    }
  }, [stickyTop])

  return (
    <div className="relative">
      <div
        ref={floatRef}
        aria-hidden
        className={`pointer-events-none fixed z-20 hidden overflow-hidden rounded-t-xl shadow-sm ${className}`}
      />
      <div ref={scrollRef} className={`overflow-x-auto ${className}`}>
        {children}
      </div>
    </div>
  )
}
