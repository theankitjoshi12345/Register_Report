import { Plus, Trash2 } from 'lucide-react'
import type { CatalogSlot, FieldErrors, FormState, ItemKey, LineItem, ScratchOff } from './report'

export const inputClass = 'min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 py-3 text-base outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-100 aria-invalid:border-rose-600 sm:text-sm'
export const buttonClass = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:opacity-50'
export const primaryClass = `${buttonClass} border-teal-800 bg-teal-800 text-white hover:bg-teal-900`

export function FieldError({ name, errors }: { name: string; errors: FieldErrors }) {
  const message = errors[name]
  return message ? <p id={`${name}-error`} className="mt-2 text-sm text-rose-800">{message}</p> : null
}

export function Amount({ name, label, value, signed, explicitSign, onChange, errors }: {
  name: string; label: string; value: string; signed?: boolean; explicitSign?: boolean; onChange: (value: string) => void; errors: FieldErrors
}) {
  const sign = value.trim().startsWith('-') ? '-' : '+'
  const magnitude = signed ? value.trim().replace(/^[+-]/, '') : value
  const updateSignedValue = (nextSign: string, nextMagnitude: string) => {
    if (!nextMagnitude) {
      onChange(nextSign === '-' ? '-' : explicitSign ? '+' : '')
    } else {
      onChange(nextSign === '-' ? `-${nextMagnitude}` : explicitSign ? `+${nextMagnitude}` : nextMagnitude)
    }
  }
  return (
    <div>
      <label htmlFor={name} className="mb-2 block text-sm font-medium text-slate-700">{label}</label>
      <div className="flex gap-2">
        {signed && <select aria-label={`${label} sign`} value={sign} onChange={(event) => updateSignedValue(event.target.value, magnitude)}
          className="min-h-12 w-[4.5rem] shrink-0 rounded-xl border border-slate-300 bg-white px-3 py-3 text-base font-semibold outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-100 sm:text-sm">
          <option value="+">+</option><option value="-">−</option>
        </select>}
        <div className="relative min-w-0 flex-1">
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">$</span>
          <input id={name} name={name} required type="number" inputMode="decimal" step="0.01" min="0"
            placeholder={signed ? '25.00' : undefined}
            value={magnitude} onChange={(event) => signed ? updateSignedValue(sign, event.target.value) : onChange(event.target.value)}
            aria-invalid={Boolean(errors[name])} aria-describedby={errors[name] ? `${name}-error` : undefined}
            className={`${inputClass} pl-7`} />
        </div>
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
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold">{title}</h3>
        <button type="button" aria-label={`Add ${title.toLowerCase()} amount`} onClick={() => onChange([...values, { amount: '', description: '' }])}
          className={`${buttonClass} px-3 py-2 text-xs text-teal-800`}><Plus size={14} /> Add amount</button>
      </div>
      <FieldError name={name} errors={errors} />
      {name === 'tickets' && <p className="mb-4 text-sm text-slate-600">Choose <strong>+</strong> when the customer was charged and <strong>−</strong> when the customer paid the store.</p>}
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
            className={`${buttonClass} mt-1 w-full self-start px-3 text-slate-500 hover:text-rose-700 sm:mt-7 sm:w-auto`}><Trash2 size={17} /><span className="sm:sr-only">Remove</span></button>
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
      <p className="mb-5 text-sm text-slate-600">For a slot with no earlier reading, the starting counter defaults to 000. An ending counter of 006 therefore counts six ticket steps. An empty entry counts no sales.</p>
      <FieldError name="scratch_offs" errors={errors} />
      <div className="rounded-2xl border border-slate-200 bg-slate-50/60 md:overflow-x-auto md:bg-white">
        <table className="block w-full text-left text-sm md:table md:min-w-[530px]">
          <thead className="hidden bg-slate-50 text-xs text-slate-600 md:table-header-group"><tr><th className="px-4 py-3">Slot / price</th><th className="px-4 py-3">Last ticket sold</th><th className="px-4 py-3">New rolls added</th></tr></thead>
          <tbody className="grid gap-3 p-3 md:table-row-group md:p-0">{form.scratch_offs.map((item, index) => {
            const slot = catalog.find((row) => row.slot_number === item.slot_number)
            const updateRow = (change: Partial<ScratchOff>) => onChange(form.scratch_offs.map((row, rowIndex) => rowIndex === index ? { ...row, ...change, recorded: true } : row))
            const endingName = `scratch_offs.${index}.ending_number`
            const rollsName = `scratch_offs.${index}.new_roll_count`
            return (
              <tr className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm md:table-row md:rounded-none md:border-0 md:border-t md:border-slate-100 md:p-0 md:shadow-none" key={item.slot_number}>
                <th scope="row" className="col-span-2 flex items-center justify-between md:table-cell md:px-4 md:py-3"><span className="block">Slot #{item.slot_number}</span><span className="font-normal text-slate-500">${slot?.ticket_price ?? '—'}</span></th>
                <td className="p-0 md:px-4 md:py-3">
                  <label htmlFor={endingName} className="mb-2 block text-xs font-medium text-slate-600 md:sr-only">Last ticket sold</label>
                  <input id={endingName} name={endingName} aria-label={`Slot ${item.slot_number} ending number`} type="text" inputMode="numeric" pattern="[0-9]*" maxLength={3}
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
                <td className="w-auto p-0 md:w-40 md:px-4 md:py-3">
                  <label htmlFor={rollsName} className="mb-2 block text-xs font-medium text-slate-600 md:sr-only">New rolls added</label>
                  <input id={rollsName} name={rollsName} aria-label={`Slot ${item.slot_number} new rolls added`} required type="number" min="0" max="32766" step="1"
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
