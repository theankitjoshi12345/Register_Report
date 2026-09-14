import { Check, CircleAlert, Pencil, Plus, WalletCards } from 'lucide-react'
import { buttonClass, primaryClass } from './FormFields'
import { fields, formFromReport, itemGroups, money } from './report'
import type { Comparison, Report } from './report'
import VerifoneBalance, { BodegaBalance } from './RegisterBalance'

function ComparisonRow({ label, value }: { label: string; value: Comparison }) {
  return (
    <tr className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-xl border border-slate-200 p-4 sm:table-row sm:rounded-none sm:border-0 sm:border-b sm:border-slate-100 sm:p-0 sm:last:border-0">
      <th scope="row" className="col-span-2 text-left font-semibold sm:table-cell sm:py-4 sm:pr-4">{label}</th>
      <td className="min-w-0 sm:table-cell sm:px-3 sm:py-4"><span className="block text-xs text-slate-500 sm:hidden">Terminal / machine</span><span className="break-words">{money(value.expected)}</span></td>
      <td className="min-w-0 sm:table-cell sm:px-3 sm:py-4"><span className="block text-xs text-slate-500 sm:hidden">Registers</span><span className="break-words">{money(value.actual)}</span></td>
      <td className="col-span-2 mt-1 flex items-center justify-between gap-2 border-t border-slate-100 pt-3 sm:table-cell sm:border-0 sm:py-4 sm:pl-3"><span className="text-xs text-slate-500 sm:hidden">Difference</span><span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${value.status === 'match' ? 'bg-teal-50 text-teal-800' : 'bg-amber-50 text-amber-800'}`}>
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
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4 sm:mb-8">
        <div className="min-w-0">
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-teal-700">{report.close_type === 'day' ? 'Legacy day close' : 'Shift close'}</p>
          <h1 className="text-2xl font-bold sm:text-3xl">{report.close_type === 'day' ? 'Legacy report' : 'Shift report'} for {report.report_date}</h1>
          {report.close_label && <p className="mt-2 break-words text-slate-600">{report.close_label}</p>}
        </div>
        <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto">
          <button type="button" onClick={() => onEdit(report)} className={`${buttonClass} w-full sm:w-auto`}><Pencil size={16} /> Edit</button>
          <button type="button" onClick={onNew} className={`${primaryClass} w-full sm:w-auto`}><Plus size={16} /> New close</button>
        </div>
      </div>
      {calculated.registers.gas_net_difference == null && <p role="status" className="mb-5 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">This older report needs its card payment amount. Edit the report to complete the Verifone balance.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl bg-slate-950 p-5 text-white">
          <h2 className="text-sm text-slate-300">Register Balances</h2>
          <dl className="mt-5 grid gap-4 min-[360px]:grid-cols-2">
            <div className="min-w-0"><dt className="text-sm text-slate-400">Bodega AI Register Balance</dt><dd className="break-words"><BodegaBalance value={calculated.registers.bodega_ai_register_balance ?? calculated.registers.bodega_net_difference} large /></dd></div>
            <div className="min-w-0"><dt className="text-sm text-slate-400">Verifone Register Balance</dt><dd className="break-words"><VerifoneBalance value={calculated.registers.gas_net_difference} large /></dd></div>
          </dl>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><WalletCards size={17} /> Scratch-off sales</h2>
          <p className="mt-5 break-words text-2xl font-bold sm:text-3xl">{money(calculated.scratch_off.sales)}</p>
        </section>
      </div>
      {report.close_type === 'shift' && calculated.terminal && <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <h2 className="text-xl font-bold">Lottery terminal for this shift</h2>
        <p className="mt-2 text-sm text-slate-600">The entered reading is cumulative. This shift's amount is the current reading minus the previous shift's cumulative reading.</p>
        <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div><dt className="text-xs text-slate-500">Previous cumulative sales</dt><dd className="font-semibold">{money(calculated.terminal.previous_cumulative_sales)}</dd></div>
          <div><dt className="text-xs text-slate-500">Current cumulative sales</dt><dd className="font-semibold">{money(calculated.terminal.cumulative_sales)}</dd></div>
          <div><dt className="text-xs text-slate-500">Sales assigned to this shift</dt><dd className="font-semibold">{money(calculated.terminal.shift_sales)}</dd></div>
          <div><dt className="text-xs text-slate-500">Previous cumulative payout</dt><dd className="font-semibold">{money(calculated.terminal.previous_cumulative_payout)}</dd></div>
          <div><dt className="text-xs text-slate-500">Current cumulative payout</dt><dd className="font-semibold">{money(calculated.terminal.cumulative_payout)}</dd></div>
          <div><dt className="text-xs text-slate-500">Payout assigned to this shift</dt><dd className="font-semibold">{money(calculated.terminal.shift_payout)}</dd></div>
        </dl>
      </section>}
      <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <h2 className="text-xl font-bold">Reconciliation</h2>
        <div><table className="mt-3 block w-full text-sm sm:table sm:min-w-[520px]">
          <thead className="hidden sm:table-header-group"><tr className="text-left text-xs uppercase text-slate-500"><th className="py-2">Comparison</th><th className="px-3">Terminal / machine</th><th className="px-3">Registers</th><th className="pl-3">Difference</th></tr></thead>
          <tbody className="grid gap-3 sm:table-row-group"><ComparisonRow label="Phone card sales" value={calculated.comparisons.phone_card_sales} /><ComparisonRow label="Lottery sales (scratch-offs + terminal)" value={calculated.comparisons.lottery_sales} /><ComparisonRow label="Lottery payout" value={calculated.comparisons.lottery_payout} /></tbody>
        </table></div>
      </section>
      <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <h2 className="text-xl font-bold">Entered figures</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div><dt className="text-xs text-slate-500">Business date</dt><dd className="font-semibold">{report.report_date}</dd></div>
          <div><dt className="text-xs text-slate-500">Close type</dt><dd className="font-semibold">{report.close_type === 'day' ? 'Legacy day close' : 'Shift close'}</dd></div>
          <div><dt className="text-xs text-slate-500">Close name</dt><dd className="font-semibold">{report.close_label || 'None'}</dd></div>
          {fields.map(([key, label]) => <div className="min-w-0" key={key}><dt className="text-xs text-slate-500">{key === 'bodega_net_difference' ? 'Bodega net difference (entered)' : label}</dt><dd className="break-words font-semibold">{money(calculated.inputs[key])}</dd></div>)}
          <div className="min-w-0"><dt className="text-xs text-slate-500">Total Bodega AI ticket amount</dt><dd className="break-words font-semibold">{money(calculated.registers.bodega_ai_ticket_total ?? '0.00')}</dd></div>
        </dl>
        <div className="mt-7 grid gap-5 md:grid-cols-3">{itemGroups.map(({ key, title }) => (
          <section key={key} aria-label={`Entered ${title.toLowerCase()}`} className="rounded-xl bg-slate-50 p-4">
            <h3 className="font-semibold">{title}</h3>
            {entered[key].length === 0 ? <p className="mt-2 text-sm text-slate-500">None</p> : <ul className="mt-2 space-y-3">{entered[key].map((item, index) => <li key={index} className="text-sm"><strong>{money(item.amount)}</strong>{item.description && <p className="mt-1 break-words text-slate-600">{item.description}</p>}</li>)}</ul>}
          </section>
        ))}</div>
        <h3 className="mb-3 mt-7 font-semibold">Scratch-off entries</h3>
        <div><table className="block w-full text-left text-sm md:table">
          <thead className="hidden md:table-header-group"><tr className="border-b text-xs text-slate-500"><th className="py-2 pr-3">Slot</th><th className="px-3">Starting number</th><th className="px-3">Ending number</th><th className="px-3">New rolls added</th><th className="pl-3">Value generated</th></tr></thead>
          <tbody className="grid gap-3 md:table-row-group">{entered.scratch_offs.map((row) => {
            const result = calculated.scratch_off.slots?.[String(row.slot_number)]
            const notRecorded = row.recorded === false || !result
            return <tr key={row.slot_number} className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 p-4 md:table-row md:rounded-none md:border-0 md:border-b md:border-slate-100 md:p-0 md:last:border-0">
              <th scope="row" className="col-span-2 border-b border-slate-100 pb-2 md:table-cell md:border-0 md:py-2 md:pr-3">Slot #{row.slot_number}</th>
              <td className="min-w-0 md:table-cell md:px-3"><span className="block text-xs text-slate-500 md:hidden">Starting number</span><span className="break-words">{notRecorded ? 'Not recorded' : ticketNumber(result.starting_number, '000')}</span></td>
              <td className="min-w-0 md:table-cell md:px-3"><span className="block text-xs text-slate-500 md:hidden">Ending number</span><span className="break-words">{notRecorded ? 'Not recorded' : ticketNumber(result.ending_number, 'Roll sold out')}</span></td>
              <td className="min-w-0 md:table-cell md:px-3"><span className="block text-xs text-slate-500 md:hidden">New rolls added</span>{notRecorded ? '—' : result.new_roll_count}</td>
              <td className="min-w-0 font-semibold md:table-cell md:pl-3"><span className="block text-xs font-normal text-slate-500 md:hidden">Value generated</span><span className="break-words">{notRecorded ? '—' : money(result.sales)}</span></td>
            </tr>
          })}</tbody>
        </table></div>
      </section>
    </main>
  )
}
