/** The AnnRakshak emblem (farmer and shield), on a cream badge so it reads on dark headers. */
export default function BrandMark({ size = 32, className = '' }: { size?: number; className?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-xl bg-cream ring-1 ring-ochre/40 overflow-hidden ${className}`}
      style={{ width: size, height: size }}
    >
      <img src="/brand/emblem-192.png" alt="" width={size} height={size} className="w-[88%] h-[88%] object-contain" />
    </span>
  )
}
