import { useState } from 'react'
import { createPortal } from 'react-dom'

// Full-screen photo viewer for the ad detail: arrows / thumbnails to move,
// click (or the magnifier button) to zoom 2.5x, and while zoomed the visible
// part follows the mouse — a loupe over the whole photo. Keyboard (Esc,
// arrows) is handled by AdModal, which owns the current index.
export default function ImageViewer({ images, index, onIndex, onClose, title }) {
  const [zoomed, setZoomed] = useState(false)
  const [origin, setOrigin] = useState('50% 50%')
  const go = i => { setZoomed(false); onIndex((i + images.length) % images.length) }

  const follow = e => {
    const r = e.currentTarget.getBoundingClientRect()
    setOrigin(`${((e.clientX - r.left) / r.width) * 100}% ${((e.clientY - r.top) / r.height) * 100}%`)
  }

  const btn = 'w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors'

  return createPortal(
    <div className="fixed inset-0 z-[60] bg-black/90 flex flex-col" onClick={onClose}>
      {/* top bar: counter, zoom, close */}
      <div className="flex items-center justify-between px-4 py-3 text-white/80 text-sm" onClick={e => e.stopPropagation()}>
        <span>{index + 1} / {images.length}</span>
        <div className="flex items-center gap-2">
          <button className={btn} onClick={() => setZoomed(z => !z)} aria-label={zoomed ? 'Одзумирајте' : 'Зумирајте'}>
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M10.5 18a7.5 7.5 0 100-15 7.5 7.5 0 000 15z" />
              {zoomed
                ? <path strokeLinecap="round" d="M7.5 10.5h6" />
                : <path strokeLinecap="round" d="M7.5 10.5h6M10.5 7.5v6" />}
            </svg>
          </button>
          <button className={btn} onClick={onClose} aria-label="Затворете">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* photo */}
      <div className="relative flex-1 min-h-0 flex items-center justify-center px-16" onClick={e => e.stopPropagation()}>
        <div
          className={`max-w-full max-h-full overflow-hidden ${zoomed ? 'cursor-zoom-out' : 'cursor-zoom-in'}`}
          onClick={() => setZoomed(z => !z)}
          onMouseMove={zoomed ? follow : undefined}
        >
          <img
            src={images[index]}
            alt={title}
            className="max-w-full max-h-[calc(100dvh-10rem)] object-contain select-none transition-transform duration-150"
            style={{ transform: zoomed ? 'scale(2.5)' : 'none', transformOrigin: origin }}
            draggable={false}
          />
        </div>
        {images.length > 1 && (
          <>
            <button className={`${btn} absolute left-3 top-1/2 -translate-y-1/2`} onClick={() => go(index - 1)} aria-label="Претходна слика">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <button className={`${btn} absolute right-3 top-1/2 -translate-y-1/2`} onClick={() => go(index + 1)} aria-label="Следна слика">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
            </button>
          </>
        )}
      </div>

      {/* thumbnails: one centred row, scrolls sideways only when there are many */}
      {images.length > 1 && (
        <div className="px-4 py-3 overflow-x-auto scrollbar-hide" onClick={e => e.stopPropagation()}>
          <div className="flex gap-1.5 w-max mx-auto">
          {images.map((src, i) => (
            <button
              key={i}
              onClick={() => go(i)}
              className={`shrink-0 w-14 h-14 rounded-md overflow-hidden border-2 ${i === index ? 'border-white' : 'border-transparent opacity-60 hover:opacity-100'}`}
            >
              <img src={src} alt="" className="w-full h-full object-cover" />
            </button>
          ))}
          </div>
        </div>
      )}
    </div>,
    document.body
  )
}
