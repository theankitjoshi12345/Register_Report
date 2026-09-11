import { Plus, Trash2 } from 'lucide-react'
import type { CatalogSlot, FieldErrors, FormState, ItemKey, LineItem, ScratchOff } from './report'

export const inputClass = 'w-full rounded-xl border border-slate-300 bg-white px-3 py-3 text-sm outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-100 aria-invalid:border-rose-600'
export const buttonClass = 'inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 px-4 py-3 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:opacity-50'
export const primaryClass = `${buttonClass} border-teal-800 bg-teal-800 text-white hover:bg-teal-900`

export function FieldError({ name, errors }: { name: string; errors: FieldErrors }) {
  const message = errors[name]
  return message ? <p id={`${name}-error`} className="mt-2 text-sm text-rose-800">{message}</p> : null
}

export function Amount({ name, label, value, signed, explicitSign, onChange, errors }: {
  name: string; label: string; value: string; signed?: boolean; explicitSign?: boolean; onChange: (value: string) => void; errors: FieldErrors
}) {
  return (
    <div>
      <label htmlFor={name} className="mb-2 block text-sm font-medium text-slate-700">{label}</label>
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">$</span>
        <input id={name} name={name} required type={explicitSign ? 'text' : 'number'} inputMode="decimal"
          step={explicitSign ? undefined : '0.01'} min={signed ? undefined : 0}
          pattern={explicitSign ? '[+-]?(?:\\d+(?:\\.\\d{0,2})?|\\.\\d{1,2})' : undefined}
          placeholder={explicitSign ? '+25.00 or -25.00' : undefined}
          value={value} onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(errors[name])} aria-describedby={errors[name] ? `${name}-error` : undefined}
          className={`${inputClass} pl-7`} />
      </div>
      <FieldError name={name} errors={errors} />
    </div>
  )
}

export function Items({ name, title, values, onChange, errors }: {
  name: ItemKey; title: string; values: LineItem[]; onChange: (values: LineItem[]) => void; errors: FieldErrors
}) {
  return (
    <section aria-label={title} className="rounded-2xl border border-slate-200 p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="font-semibold">{title}</h3>
        <button type="button" aria-label={`Add ${title.toLowerCase()} amount`} onClick={() => onChange([...values, { amount: '', description: '' }])}
          className={`${buttonClass} px-3 py-2 text-xs text-teal-800`}><Plus size={14} /> Add amount</button>
      </div>
      <FieldError name={name} errors={errors} />
      {name === 'tickets' && <p className="mb-4 text-sm text-slate-600">Use <strong>+</strong> when the customer was charged and <strong>−</strong> when the customer paid the store.</p>}
      {values.length === 0 ? <p className="text-sm text-slate-500">Nothing added.</p> : values.map((item, index) => (
        <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_1.5fr_auto]" key={`${name}-${index}`}>
          <Amount name={`${name}.${index}.amount`} label={`${title} amount ${index + 1}`} value={item.amount}
            signed={name === 'tickets'} explicitSign={name === 'tickets'}
            errors={errors} onChange={(amount) => onChange(values.map((row, rowIndex) => rowIndex === index ? { ...row, amount } : row))} />
          <div>
            <label htmlFor={`${name}.${index}.description`} className="mb-2 block text-sm font-medium">Description (optional)</label>
            <input id={`${name}.${index}.description`} name={`${name}.${index}.description`} maxLength={255} value={item.description}
              aria-label={`${title} description ${index + 1}`} className={inputClass}
              aria-invalid={Boolean(errors[`${name}.${index}.description`])}
              aria-describedby={errors[`${name}.${index}.description`] ? `${name}.${index}.description-error` : undefined}
              onChange={(event) => onChange(values.map((row, rowIndex) => rowIndex === index ? { ...row, description: event.target.value } : row))} />
            <FieldError name={`${name}.${index}.description`} errors={errors} />
          </div>
          <button type="button" aria-label={`Remove ${title.toLowerCase()} item ${index + 1}`}
            onClick={() => onChange(values.filter((_, rowIndex) => rowIndex !== index))}
            className={`${buttonClass} mt-7 self-start px-3 text-slate-500 hover:text-rose-700`}><Trash2 size={17} /></button>
          <FieldError name={`${name}.${index}`} errors={errors} />
        </div>
      ))}
    </section>
  )
}

export function ScratchFields({ form, catalog, errors, onChange }: {
  form: FormState; catalog: CatalogSlot[]; errors: FieldErrors; onChange: (value: ScratchOff[]) => void
}) {
  const isDay = form.close_type === 'day'
  return (
    <section>
      <h2 className="text-xl font-bold">Scratch-off last tickets sold</h2>
      <p className="mb-3 mt-2 text-sm leading-6 text-slate-600">
        {isDay
          ? 'Enter the last ticket sold at the end of the day and all new rolls added during the whole business day. Day closes compare with the previous business date, including when shifts were saved today.'
          : 'Enter the last ticket sold at the end of this shift and new rolls added during this shift. Counters compare with the previous shift today, or the previous business date for the first shift.'}
      </p>
      <p className="mb-3 text-sm text-slate-600">Ending numbers must be whole numbers. 020 means ticket 020 was the last ticket sold; the remaining tickets start at 021. Leave the number empty when the roll sold out. Enter 0 new rolls when none were added.</p>
      <p className="mb-3 text-sm text-slate-600">If tonight's ending number is lower than the prior ending number, the report automatically counts one new roll unless you enter a larger number of new rolls.</p>
      <p className="mb-5 text-sm text-slate-600">For a slot with no earlier reading, an empty entry counts no sales. Its first ticket number counts sales from 000, so enter accurate opening history before your first close.</p>
      <FieldError name="scratch_offs" errors={errors} />
      <div className="overflow-x-auto rounded-2xl border border-slate-200">
        <table className="w-full min-w-[530px] text-left text-sm">
          <thead className="bg-slate-50 text-xs text-slate-600"><tr><th className="px-4 py-3">Slot / price</th><th className="px-4 py-3">Last ticket sold</th><th className="px-4 py-3">New rolls added</th></tr></thead>
          <tbody>{form.scratch_offs.map((item, index) => {
            const slot = catalog.find((row) => row.slot_number === item.slot_number)
            const updateRow = (change: Partial<ScratchOff>) => onChange(form.scratch_offs.map((row, rowIndex) => rowIndex === index ? { ...row, ...change, recorded: true } : row))
            const endingName = `scratch_offs.${index}.ending_number`
            const rollsName = `scratch_offs.${index}.new_roll_count`
            return (
              <tr className="border-t border-slate-100" key={item.slot_number}>
                <th scope="row" className="px-4 py-3"><span className="block">#{item.slot_number}</span><span className="font-normal text-slate-500">${slot?.ticket_price ?? '—'}</span></th>
                <td className="px-4 py-3">
                  <input name={endingName} aria-label={`Slot ${item.slot_number} ending number`} type="text" inputMode="numeric" pattern="[0-9]*" maxLength={3}
                    placeholder={`000–${String(slot?.max_ticket_number ?? 0).padStart(3, '0')}`} value={item.ending_number}
                    aria-invalid={Boolean(errors[endingName])} aria-describedby={errors[endingName] ? `${endingName}-error` : undefined}
                    onChange={(event) => {
                      const value = event.target.value
                      if (!/^\d*$/.test(value)) {
                        event.currentTarget.value = item.ending_number
                        return
                      }
                      const tooLarge = value !== '' && slot != null && Number(value) > slot.max_ticket_number
                      event.currentTarget.setCustomValidity(tooLarge ? `Enter a whole number from 000 to ${String(slot?.max_ticket_number ?? 0).padStart(3, '0')}.` : '')
                      updateRow({ ending_number: value })
                    }} className={inputClass} />
                  {item.recorded === false && <p className="mt-2 text-xs text-slate-500">Not recorded. Leave unchanged to keep the earlier reading.</p>}
                  <FieldError name={endingName} errors={errors} /><FieldError name={`scratch_offs.${index}`} errors={errors} />
                </td>
                <td className="w-40 px-4 py-3">
                  <input name={rollsName} aria-label={`Slot ${item.slot_number} new rolls added`} required type="number" min="0" max="32766" step="1"
                    value={item.new_roll_count} onChange={(event) => updateRow({ new_roll_count: event.target.value })}
                    aria-invalid={Boolean(errors[rollsName])} aria-describedby={errors[rollsName] ? `${rollsName}-error` : undefined} className={inputClass} />
                  <FieldError name={rollsName} errors={errors} />
                </td>
              </tr>
            )
          })}</tbody>
        </table>
      </div>
    </section>
  )
}
