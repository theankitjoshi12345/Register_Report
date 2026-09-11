import { useState } from 'react'
import { Archive, ArrowRight, LogOut, Store } from 'lucide-react'
import { buttonClass, inputClass } from './FormFields'
import type { Report, Session } from './report'

export default function Header({ reports, onSelect, session, storeId, onStoreChange, onLogout }: {
  reports: Report[]; onSelect: (report: Report) => void; session: Session | null; storeId: number | null
  onStoreChange: (id: number) => void; onLogout: () => void
}) {
  const [historyDate, setHistoryDate] = useState('')
  const matches = reports.filter((report) => !historyDate || report.report_date === historyDate)
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex min-h-20 max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-8">
        <a href="/" className="flex items-center gap-3"><span className="flex size-10 items-center justify-center rounded-xl bg-teal-900 text-white"><Store size={21} /></span><strong>Register Report</strong></a>
        {session?.user && <div className="flex flex-wrap items-center gap-2">
          {session.stores.length > 1 ? <label><span className="sr-only">Store</span><select aria-label="Store" value={storeId ?? ''} onChange={(event) => onStoreChange(Number(event.target.value))} className={`${inputClass} py-2`}>{session.stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></label> : <span className="text-sm text-slate-600">{session.stores[0]?.name}</span>}
          <details className="relative">
            <summary className={`${buttonClass} cursor-pointer list-none py-2`}><Archive size={16} /> History <span className="text-xs text-slate-500">{reports.length}</span></summary>
            <div className="absolute right-0 z-10 mt-2 max-h-[70vh] w-[min(20rem,85vw)] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-xl">
              <label className="block p-2 text-sm font-medium">Filter by business date<input type="date" value={historyDate} onChange={(event) => setHistoryDate(event.target.value)} className={`${inputClass} mt-2`} /></label>
              {historyDate && <button type="button" onClick={() => setHistoryDate('')} className="px-3 py-2 text-sm text-teal-800">Clear date filter</button>}
              {matches.length === 0 && <p className="p-3 text-sm text-slate-500">{reports.length ? 'No reports for this date.' : 'No saved reports yet.'}</p>}
              {matches.map((report) => <button type="button" key={report.id} onClick={(event) => { onSelect(report); event.currentTarget.closest('details')?.removeAttribute('open') }} className="flex w-full items-center justify-between gap-3 rounded-xl p-3 text-left hover:bg-teal-50"><span><strong className="block text-sm">{report.report_date}</strong><small className="text-slate-500">{report.close_type} {report.close_label}</small></span><ArrowRight size={15} /></button>)}
            </div>
          </details>
          <button type="button" onClick={onLogout} className={`${buttonClass} py-2`} aria-label={`Sign out ${session.user.username}`}><LogOut size={16} /><span className="hidden sm:inline">Sign out</span></button>
        </div>}
      </div>
    </header>
  )
}
