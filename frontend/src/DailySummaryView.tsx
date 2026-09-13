import { ArrowRight, Check, CircleAlert, Plus } from 'lucide-react'
import { buttonClass, primaryClass } from './FormFields'
import { bodegaFields, gasFields, independentFields, itemGroups, money } from './report'
import type { Comparison, DailySummary } from './report'

function ComparisonRow({ label, value }: { label: string; value: Comparison }) {
  return <tr className="grid grid-cols-2 gap-2 rounded-xl border border-slate-200 p-4 sm:table-row sm:border-0 sm:border-b sm:border-slate-100 sm:p-0">
    <th className="col-span-2 text-left sm:table-cell sm:py-4">{label}</th>
    <td className="sm:px-3"><span className="block text-xs text-slate-500 sm:hidden">Terminal / machine</span>{money(value.expected)}</td>
    <td className="sm:px-3"><span className="block text-xs text-slate-500 sm:hidden">Registers</span>{money(value.actual)}</td>
    <td className="col-span-2 sm:pl-3"><span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${value.status === 'match' ? 'bg-teal-50 text-teal-800' : 'bg-amber-50 text-amber-800'}`}>{value.status === 'match' ? <Check size={13} /> : <CircleAlert size={13} />}{value.status === 'match' ? 'Matches' : `Off ${money(value.difference)}`}</span></td>
  </tr>
}

export default function DailySummaryView({ summary, onOpenShift, onNewShift }: {
  summary: DailySummary; onOpenShift: (id: number) => void; onNewShift: () => void
}) {
  const combinedFields = [...independentFields.slice(2), ...bodegaFields.filter(([key]) => key !== 'bodega_net_difference'), ...gasFields]
  const scratchSlots = Object.entries(summary.scratch_off.final_state).sort(([left], [right]) => Number(left) - Number(right))
  return <main className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div><p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-teal-700">Automatic day end</p><h1 className="text-2xl font-bold sm:text-3xl">Daily summary for {summary.report_date}</h1><p className="mt-2 text-slate-600">Calculated from {summary.shift_count} {summary.shift_count === 1 ? 'shift' : 'shifts'}.</p></div>
      <button type="button" onClick={onNewShift} className={`${primaryClass} w-full sm:w-auto`}><Plus size={16} /> New shift</button>
    </div>

    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <section className="rounded-2xl bg-slate-950 p-5 text-white"><p className="text-sm text-slate-400">Final terminal sales</p><strong className="mt-2 block text-2xl">{money(summary.terminal.final_cumulative_sales)}</strong></section>
      <section className="rounded-2xl bg-slate-950 p-5 text-white"><p className="text-sm text-slate-400">Final terminal payout</p><strong className="mt-2 block text-2xl">{money(summary.terminal.final_cumulative_payout)}</strong></section>
      <section className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Scratch-off sales</p><strong className="mt-2 block text-2xl">{money(summary.scratch_off.sales)}</strong></section>
      <section className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">New rolls</p><strong className="mt-2 block text-2xl">{summary.scratch_off.total_new_rolls}</strong></section>
    </div>

    <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
      <h2 className="text-xl font-bold">Day-end reconciliation</h2>
      <table className="mt-3 block w-full text-sm sm:table"><thead className="hidden text-left text-xs uppercase text-slate-500 sm:table-header-group"><tr><th className="py-2">Comparison</th><th className="px-3">Terminal / machine</th><th className="px-3">Registers</th><th className="pl-3">Difference</th></tr></thead><tbody className="grid gap-3 sm:table-row-group"><ComparisonRow label="Lottery sales" value={summary.comparisons.lottery_sales} /><ComparisonRow label="Lottery payout" value={summary.comparisons.lottery_payout} /><ComparisonRow label="Phone-card sales" value={summary.comparisons.phone_card_sales} /></tbody></table>
    </section>

    <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
      <h2 className="text-xl font-bold">Shifts</h2>
      <div className="mt-4 grid gap-3 md:grid-cols-2">{summary.shifts.map((shift, index) => <button type="button" key={shift.id} onClick={() => onOpenShift(shift.id)} className={`${buttonClass} justify-between p-4 text-left`}><span><strong className="block">{shift.close_label || `Shift ${index + 1}`}</strong><small className="text-slate-500">Terminal sales {money(shift.terminal_sales)} · Scratch-offs {money(shift.scratch_off_sales)}</small></span><ArrowRight size={16} /></button>)}</div>
    </section>

    <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
      <h2 className="text-xl font-bold">Combined shift figures</h2>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {combinedFields.map(([key, label]) => <div key={key}><dt className="text-xs text-slate-500">{label.replace('Current cumulative ', '')}</dt><dd className="font-semibold">{money(summary.inputs[key])}</dd></div>)}
        <div><dt className="text-xs text-slate-500">Register Balance</dt><dd className="font-semibold">{money(summary.registers.bodega_ai_register_balance)}</dd></div>
        <div><dt className="text-xs text-slate-500">Combined Bodega net difference (entered)</dt><dd className="font-semibold">{money(summary.registers.bodega_net_difference)}</dd></div>
        <div><dt className="text-xs text-slate-500">Total Bodega AI ticket amount</dt><dd className="font-semibold">{money(summary.registers.bodega_ai_ticket_total)}</dd></div>
        <div><dt className="text-xs text-slate-500">Combined Verifone net difference</dt><dd className="font-semibold">{money(summary.registers.gas_net_difference)}</dd></div>
      </dl>
      <div className="mt-7 grid gap-4 md:grid-cols-3">{itemGroups.map(({ key, title }) => <section key={key} className="rounded-xl bg-slate-50 p-4"><h3 className="font-semibold">{title}</h3><p className="mt-2 text-xl font-bold">{money(summary.line_items[key].total)}</p>{summary.line_items[key].entries.length > 0 && <ul className="mt-3 space-y-2 text-sm">{summary.line_items[key].entries.map((entry, index) => <li key={`${entry.report_id}-${index}`}><strong>{money(entry.amount)}</strong>{entry.description && <span className="ml-2 text-slate-600">{entry.description}</span>}</li>)}</ul>}</section>)}</div>
    </section>

    <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
      <h2 className="text-xl font-bold">Final scratch-off state</h2>
      {scratchSlots.length === 0 ? <p className="mt-3 text-sm text-slate-500">No scratch-off counters have been recorded.</p> : <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{scratchSlots.map(([slot, state]) => <div key={slot} className="rounded-xl bg-slate-50 p-4"><strong>Slot #{slot}</strong><p className="mt-1 text-sm text-slate-600">{state.ending_exhausted ? 'Roll sold out' : `Ending ${String(state.ending_number ?? 0).padStart(3, '0')}`}</p><p className="mt-1 text-xs text-slate-500">New rolls today: {summary.scratch_off.new_rolls_by_slot[slot] ?? 0}</p></div>)}</div>}
    </section>
  </main>
}
