import { Check, CircleAlert, Pencil, Plus, WalletCards } from 'lucide-react'
import { buttonClass, primaryClass } from './FormFields'
import { fields, formFromReport, itemGroups, money } from './report'
import type { Comparison, Report } from './report'

function ComparisonRow({ label, value }: { label: string; value: Comparison }) {
  return (
    <tr className="border-b border-slate-100 last:border-0">
      <th scope="row" className="py-4 pr-4 text-left font-semibold">{label}</th>
      <td className="px-3 py-4">{money(value.expected)}</td>
      <td className="px-3 py-4">{money(value.actual)}</td>
      <td className="py-4 pl-3"><span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${value.status === 'match' ? 'bg-teal-50 text-teal-800' : 'bg-amber-50 text-amber-800'}`}>
        {value.status === 'match' ? <Check size={13} /> : <CircleAlert size={13} />}
        {value.status === 'match' ? 'Matches' : value.status === 'incomplete' ? 'Needs entry' : `Off ${money(value.difference)}`}
      </span></td>
    </tr>
  )
}

const ticketNumber = (value: number | null | undefined, empty: string) => value == null ? empty : String(value).padStart(3, '0')

export default function ReportView({ report, onEdit, onNew }: { report: Report; onEdit: (report: Report) => void; onNew: () => void }) {
  const { calculated } = report
  const entered = formFromReport(report)
  return (
    <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-teal-700">{report.close_type} close</p>
          <h1 className="text-3xl font-bold">Report for {report.report_date}</h1>
          {report.close_label && <p className="mt-2 text-slate-600">{report.close_label}</p>}
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => onEdit(report)} className={buttonClass}><Pencil size={16} /> Edit</button>
          <button type="button" onClick={onNew} className={primaryClass}><Plus size={16} /> New close</button>
        </div>
      </div>
      {calculated.registers.gas_net_difference == null && <p role="status" className="mb-5 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">This older report needs its card payment amount. Edit the report to complete the Verifone balance.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl bg-slate-950 p-5 text-white">
          <h2 className="text-sm text-slate-300">Register balance</h2>
          <dl className="mt-5 grid grid-cols-2 gap-4">
            <div><dt className="text-sm text-slate-400">Bodega AI</dt><dd className="text-2xl font-bold">{money(calculated.registers.bodega_net_difference)}</dd></div>
            <div><dt className="text-sm text-slate-400">Verifone</dt><dd className="text-2xl font-bold">{money(calculated.registers.gas_net_difference)}</dd></div>
          </dl>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><WalletCards size={17} /> Scratch-off sales</h2>
          <p className="mt-5 text-3xl font-bold">{money(calculated.scratch_off.sales)}</p>
        </section>
      </div>
      <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <h2 className="text-xl font-bold">Reconciliation</h2>
        <div className="overflow-x-auto"><table className="mt-3 w-full min-w-[520px] text-sm">
          <thead><tr className="text-left text-xs uppercase text-slate-500"><th className="py-2">Comparison</th><th className="px-3">Expected</th><th className="px-3">Actual</th><th className="pl-3">Difference</th></tr></thead>
          <tbody><ComparisonRow label="Phone card sales" value={calculated.comparisons.phone_card_sales} /><ComparisonRow label="Lottery sales" value={calculated.comparisons.lottery_sales} /><ComparisonRow label="Lottery payout" value={calculated.comparisons.lottery_payout} /></tbody>
        </table></div>
      </section>
      <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <h2 className="text-xl font-bold">Entered figures</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div><dt className="text-xs text-slate-500">Business date</dt><dd className="font-semibold">{report.report_date}</dd></div>
          <div><dt className="text-xs text-slate-500">Close type</dt><dd className="font-semibold">{report.close_type === 'day' ? 'Day close' : 'Shift close'}</dd></div>
          <div><dt className="text-xs text-slate-500">Close name</dt><dd className="font-semibold">{report.close_label || 'None'}</dd></div>
          {fields.map(([key, label]) => <div key={key}><dt className="text-xs text-slate-500">{label}</dt><dd className="font-semibold">{money(calculated.inputs[key])}</dd></div>)}
        </dl>
        <div className="mt-7 grid gap-5 md:grid-cols-3">{itemGroups.map(({ key, title }) => (
          <section key={key} aria-label={`Entered ${title.toLowerCase()}`} className="rounded-xl bg-slate-50 p-4">
            <h3 className="font-semibold">{title}</h3>
            {entered[key].length === 0 ? <p className="mt-2 text-sm text-slate-500">None</p> : <ul className="mt-2 space-y-3">{entered[key].map((item, index) => <li key={index} className="text-sm"><strong>{money(item.amount)}</strong>{item.description && <p className="mt-1 break-words text-slate-600">{item.description}</p>}</li>)}</ul>}
          </section>
        ))}</div>
        <h3 className="mb-3 mt-7 font-semibold">Scratch-off entries</h3>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead><tr className="border-b text-xs text-slate-500"><th className="py-2 pr-3">Slot</th><th className="px-3">Starting number</th><th className="px-3">Ending number</th><th className="px-3">New rolls added</th><th className="pl-3">Value generated</th></tr></thead>
          <tbody>{entered.scratch_offs.map((row) => {
            const result = calculated.scratch_off.slots?.[String(row.slot_number)]
            const notRecorded = row.recorded === false || !result
            return <tr key={row.slot_number} className="border-b border-slate-100 last:border-0">
              <th scope="row" className="py-2 pr-3">#{row.slot_number}</th>
              <td className="px-3">{notRecorded ? 'Not recorded' : ticketNumber(result.starting_number, '000')}</td>
              <td className="px-3">{notRecorded ? 'Not recorded' : ticketNumber(result.ending_number, 'Roll sold out')}</td>
              <td className="px-3">{notRecorded ? '—' : result.new_roll_count}</td>
              <td className="pl-3 font-semibold">{notRecorded ? '—' : money(result.sales)}</td>
            </tr>
          })}</tbody>
        </table></div>
      </section>
    </main>
  )
}
