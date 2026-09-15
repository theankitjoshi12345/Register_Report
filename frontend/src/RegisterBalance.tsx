import { displayedBodegaBalance, displayedVerifoneBalance } from './report'

function RegisterBalance({ value, helper, large, format }: {
  value: string | null; helper: string; large: boolean; format: (value: string | null) => string
}) {
  const balance = format(value)
  return <span className="block">
    <strong aria-label={balance} className={`block break-words font-bold ${large ? 'text-xl sm:text-2xl' : ''}`}>{balance}</strong>
    <small className="mt-1 block text-xs font-normal text-slate-400">{helper}</small>
  </span>
}

export function BodegaBalance({ value, large = false }: { value: string | null; large?: boolean }) {
  return <RegisterBalance value={value} helper="+ short / − over" large={large} format={displayedBodegaBalance} />
}

export default function VerifoneBalance({ value, large = false }: { value: string | null; large?: boolean }) {
  return <RegisterBalance value={value} helper="+ short / − over" large={large} format={displayedVerifoneBalance} />
}
