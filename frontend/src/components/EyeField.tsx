import { useEffect, useRef } from 'react'

/**
 * The hero's eye ("nazar"): an almond eye drawn as a grid of English and Hindi
 * characters on a canvas. It blinks, its pupil breathes and it glances toward
 * the pointer. Decorative only; it draws a single still frame when the viewer
 * prefers reduced motion and pauses while off screen or in a hidden tab.
 */

const GLYPHS = Array.from('नजरसमचखबदशभतवकपलहयडगNAZRSTOYEWV0123456789')
const CELL_W = 9
const CELL_H = 12
const TILT = (-16 * Math.PI) / 180
const FRAME_MS = 1000 / 30

type RGB = [number, number, number]
// newspaper inks: black, a red spot colour, greys, and the paper itself
const RED: RGB = [165, 87, 74]
const INK: RGB = [58, 54, 49]
const GREY: RGB = [110, 106, 98]
const FAINT: RGB = [150, 145, 133]
const PAPER: RGB = [243, 240, 232]

function mix(a: RGB, b: RGB, t: number): RGB {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

export default function EyeField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let width = 0
    let height = 0
    let cols = 0
    let rows = 0
    let glyphs: number[] = []
    let seeds: number[] = []

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = rect.width
      height = rect.height
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      cols = Math.ceil(width / CELL_W)
      rows = Math.ceil(height / CELL_H)
      glyphs = Array.from({ length: cols * rows }, () => Math.floor(Math.random() * GLYPHS.length))
      seeds = Array.from({ length: cols * rows }, () => Math.random())
    }

    // gaze: eased toward the pointer, wandering slowly when it is idle
    const gaze = { x: 0, y: 0, tx: 0, ty: 0, lastMove: -10 }
    const onPointer = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      const dx = e.clientX - (rect.left + rect.width / 2)
      const dy = e.clientY - (rect.top + rect.height / 2)
      const len = Math.hypot(dx, dy) || 1
      const reach = Math.min(1, len / 600)
      gaze.tx = (dx / len) * reach
      gaze.ty = (dy / len) * reach
      gaze.lastMove = performance.now() / 1000
    }

    let nextBlink = 2.5
    const blinkLength = 0.32

    const draw = (t: number) => {
      ctx.clearRect(0, 0, width, height)
      const size = Math.min(width, height)
      const cx = width / 2
      const cy = height / 2
      const eyeW = Math.min(width * 0.42, size * 0.52)
      const irisR = size * 0.17

      // blink
      let open = 1
      if (!reduced) {
        if (t > nextBlink + blinkLength) nextBlink = t + 3.5 + Math.random() * 4
        if (t >= nextBlink) open = Math.max(0.05, 1 - Math.sin(((t - nextBlink) / blinkLength) * Math.PI))
      }
      const eyeH = size * 0.23 * open

      // gaze target: pointer when recently moved, otherwise a slow wander
      if (t - gaze.lastMove > 2.5) {
        gaze.tx = Math.sin(t * 0.37) * 0.5
        gaze.ty = Math.sin(t * 0.23 + 1) * 0.35
      }
      gaze.x += (gaze.tx - gaze.x) * 0.06
      gaze.y += (gaze.ty - gaze.y) * 0.06
      const irisX = cx + gaze.x * size * 0.07
      const irisY = cy + gaze.y * size * 0.045
      const pupilR = irisR * (0.38 + 0.06 * Math.sin(t * 0.7))

      const cos = Math.cos(TILT)
      const sin = Math.sin(TILT)

      // underlay: the almond, iris and pupil as soft shapes beneath the glyphs
      ctx.save()
      ctx.beginPath()
      for (let k = 0; k <= 64; k++) {
        const u = -1 + (2 * k) / 64
        const lx = u * eyeW
        const ly = -Math.pow(1 - u * u, 0.78) * eyeH
        ctx.lineTo(cx + lx * cos - ly * sin, cy + lx * sin + ly * cos)
      }
      for (let k = 64; k >= 0; k--) {
        const u = -1 + (2 * k) / 64
        const lx = u * eyeW
        const ly = Math.pow(1 - u * u, 0.78) * eyeH
        ctx.lineTo(cx + lx * cos - ly * sin, cy + lx * sin + ly * cos)
      }
      ctx.closePath()
      ctx.fillStyle = 'rgba(251, 250, 246, 0.9)'
      ctx.fill()
      ctx.lineWidth = 1.2
      ctx.strokeStyle = 'rgba(58, 54, 49, 0.55)'
      ctx.stroke()
      ctx.clip()
      const iris = ctx.createRadialGradient(irisX, irisY, pupilR * 0.8, irisX, irisY, irisR)
      iris.addColorStop(0, 'rgba(165, 87, 74, 0.22)')
      iris.addColorStop(0.5, 'rgba(20, 20, 20, 0.05)')
      iris.addColorStop(0.9, 'rgba(20, 20, 20, 0.08)')
      iris.addColorStop(1, 'rgba(58, 54, 49, 0.3)')
      ctx.fillStyle = iris
      ctx.beginPath()
      ctx.arc(irisX, irisY, irisR, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = 'rgba(58, 54, 49, 0.85)'
      ctx.beginPath()
      ctx.arc(irisX, irisY, pupilR, 0, Math.PI * 2)
      ctx.fill()
      // catch-light
      ctx.fillStyle = 'rgba(243, 240, 232, 0.7)'
      ctx.beginPath()
      ctx.arc(irisX - pupilR * 0.45, irisY - pupilR * 0.5, pupilR * 0.16, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()

      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.font = "600 9.5px 'Libre Franklin', Mukta, system-ui, sans-serif"

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const i = r * cols + c
          const x = c * CELL_W + CELL_W / 2
          const y = r * CELL_H + CELL_H / 2
          // eye-local, rotated coordinates
          const dx = x - cx
          const dy = y - cy
          const px = dx * cos + dy * sin
          const py = -dx * sin + dy * cos
          const u = px / eyeW
          const seed = seeds[i]

          let color: RGB = FAINT
          let alpha = 0
          const lid = Math.abs(u) < 1 ? Math.pow(1 - u * u, 0.78) * eyeH : 0
          const d = lid > 0 ? Math.abs(py) / lid : Infinity

          if (d < 1) {
            const ix = x - irisX
            const iy = y - irisY
            const rr = Math.hypot(ix, iy)
            if (rr < pupilR) {
              color = PAPER
              alpha = 0.3 + 0.3 * seed
            } else if (rr < irisR) {
              const ang = Math.atan2(iy, ix)
              const radial = (rr - pupilR) / (irisR - pupilR)
              const fibre = 0.5 + 0.5 * Math.sin(ang * 23 + Math.sin(ang * 7 + t * 0.4) * 2.2 + radial * 3)
              color = radial < 0.3 ? mix(RED, INK, radial / 0.3) : radial > 0.85 ? INK : mix(INK, GREY, fibre)
              alpha = 0.45 + 0.55 * fibre
            } else {
              // sclera, a little brighter toward the rim
              color = GREY
              alpha = 0.08 + 0.06 * seed + 0.3 * Math.max(0, d - 0.75)
            }
            if (d > 0.84) {
              const rim = 1 - Math.abs(d - 0.95) / 0.12
              if (rim > 0) {
                color = mix(color, INK, rim)
                alpha = Math.max(alpha, 0.55 + 0.45 * rim)
              }
            }
          } else if (Math.abs(u) < 1.45 && Math.abs(py) < CELL_H * (0.9 - Math.abs(u) * 0.35) * Math.max(open, 0.4)) {
            // the thin tails at the eye's corners
            color = INK
            alpha = Math.max(0, 1.5 - Math.abs(u)) * 0.85
          } else if (d < 1.12 && Math.abs(u) < 1) {
            color = INK
            alpha = (1 - (d - 1) / 0.12) * 0.6
          } else {
            // background field: a faint diagonal band of shimmering characters
            const band = Math.max(0, 1 - Math.abs(py) / (size * 0.62))
            const shimmer = 0.5 + 0.5 * Math.sin(seed * 40 + t * (0.6 + seed))
            alpha = band * (0.04 + 0.12 * shimmer * shimmer)
            color = FAINT
          }

          if (alpha < 0.03) continue
          if (!reduced && Math.random() < 0.004) glyphs[i] = Math.floor(Math.random() * GLYPHS.length)
          ctx.fillStyle = `rgba(${color[0] | 0},${color[1] | 0},${color[2] | 0},${Math.min(1, alpha).toFixed(3)})`
          ctx.fillText(GLYPHS[glyphs[i]], x, y)
        }
      }
    }

    resize()
    const resizer = new ResizeObserver(() => {
      resize()
      if (reduced) draw(0)
    })
    resizer.observe(canvas)

    if (reduced) {
      draw(0)
      return () => resizer.disconnect()
    }

    let visible = true
    const seen = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting))
    seen.observe(canvas)
    window.addEventListener('pointermove', onPointer, { passive: true })

    let raf = 0
    let last = 0
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop)
      if (!visible || document.hidden || now - last < FRAME_MS) return
      last = now
      draw(now / 1000)
    }
    raf = requestAnimationFrame(loop)
    // fonts arrive after first paint; a fresh frame picks them up
    document.fonts?.ready.then(() => (last = 0))

    return () => {
      cancelAnimationFrame(raf)
      resizer.disconnect()
      seen.disconnect()
      window.removeEventListener('pointermove', onPointer)
    }
  }, [])

  return <canvas ref={ref} className={className} aria-hidden="true" />
}
