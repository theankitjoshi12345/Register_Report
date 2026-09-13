import { displayedVerifoneBalance } from './report'

export default function VerifoneBalance({ value, large = false }: { value: string | null; large?: boolean }) {
  const balance = displayedVerifoneBalance(value)
  return <strong aria-label={balance} className={`font-bold ${large ? 'text-xl sm:text-2xl' : ''}`}>{balance}</strong>
}
