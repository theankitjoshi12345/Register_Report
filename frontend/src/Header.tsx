import { useState } from 'react'
import { Archive, ArrowRight, LogOut, Store } from 'lucide-react'
import { buttonClass, inputClass } from './FormFields'
import type { DailySummary, Report, Session } from './report'

export default function Header({ reports, summaries, onSelect, onSelectSummary, session, storeId, onStoreChange, onLogout }: {
  reports: Report[]; summaries: DailySummary[]; onSelect: (report: Report) => void; onSelectSummary: (summary: DailySummary) => void; session: Session | null; storeId: number | null
  onStoreChange: (id: number) => void; onLogout: () => void
}) {
  const [historyDate, setHistoryDate] = useState('')
  const matches = reports.filter((report) => !historyDate || report.report_date === historyDate)
  const summaryMatches = summaries.filter((summary) => !historyDate || summary.report_date === historyDate)
  return (
    <header className="relative border-b border-slate-200 bg-white">
      <div className="mx-auto flex min-h-20 max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-8 sm:py-4">
        <a href="/" className="flex min-w-0 items-center gap-2.5 sm:gap-3"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-900 text-white"><Store size={21} /></span><strong className="truncate">Register Report</strong></a>
        {session?.user && <div className="flex w-full min-w-0 items-center justify-between gap-2 sm:w-auto sm:justify-end">
          {session.stores.length > 1 ? <label className="min-w-0 flex-1 sm:max-w-52"><span className="sr-only">Store</span><select aria-label="Store" value={storeId ?? ''} onChange={(event) => onStoreChange(Number(event.target.value))} className={`${inputClass} py-2`}>{session.stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></label> : <span className="min-w-0 flex-1 truncate text-sm text-slate-600 sm:flex-none">{session.stores[0]?.name}</span>}
          <details className="static shrink-0 sm:relative">
            <summary className={`${buttonClass} cursor-pointer list-none py-2`}><Archive size={16} /> History <span className="text-xs text-slate-500">{reports.length}</span></summary>
            <div className="absolute inset-x-4 top-full z-20 mt-2 max-h-[70vh] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-xl sm:inset-x-auto sm:right-0 sm:top-auto sm:w-80">
              <label className="block p-2 text-sm font-medium">Filter by business date<input type="date" value={historyDate} onChange={(event) => setHistoryDate(event.target.value)} className={`${inputClass} mt-2`} /></label>
              {historyDate && <button type="button" onClick={() => setHistoryDate('')} className="px-3 py-2 text-sm text-teal-800">Clear date filter</button>}
              {matches.length === 0 && summaryMatches.length === 0 && <p className="p-3 text-sm text-slate-500">{reports.length ? 'No reports for this date.' : 'No saved reports yet.'}</p>}
              {summaryMatches.map((summary) => <button type="button" key={`summary-${summary.report_date}`} onClick={(event) => { onSelectSummary(summary); event.currentTarget.closest('details')?.removeAttribute('open') }} className="flex w-full items-center justify-between gap-3 rounded-xl bg-teal-50 p-3 text-left hover:bg-teal-100"><span><strong className="block text-sm">{summary.report_date}</strong><small className="text-teal-800">Daily summary · {summary.shift_count} {summary.shift_count === 1 ? 'shift' : 'shifts'}</small></span><ArrowRight size={15} /></button>)}
              {matches.map((report) => <button type="button" key={report.id} onClick={(event) => { onSelect(report); event.currentTarget.closest('details')?.removeAttribute('open') }} className="flex w-full items-center justify-between gap-3 rounded-xl p-3 text-left hover:bg-teal-50"><span><strong className="block text-sm">{report.report_date}</strong><small className="text-slate-500">{report.close_type === 'day' ? 'Legacy day close' : 'Shift'} {report.close_label}</small></span><ArrowRight size={15} /></button>)}
            </div>
          </details>
          <button type="button" onClick={onLogout} className={`${buttonClass} shrink-0 px-3 py-2 sm:px-4`} aria-label={`Sign out ${session.user.username}`}><LogOut size={16} /><span className="hidden sm:inline">Sign out</span></button>
        </div>}
      </div>
    </header>
  )
}
