import { verifoneBalanceStatus } from './report'

export default function VerifoneBalance({ value, large = false }: { value: string | null; large?: boolean }) {
  const balance = verifoneBalanceStatus(value)
  return <span aria-label={balance.text} className={`inline-flex flex-wrap items-baseline gap-x-1 ${large ? 'text-xl sm:text-2xl' : ''}`}>
    <strong className="font-bold">{balance.status}</strong>
    {balance.amount && <span className="font-semibold">by {balance.amount}</span>}
  </span>
}
