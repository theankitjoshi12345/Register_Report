export type CloseType = 'day' | 'shift'
export type LineItem = { amount: string; description: string }
export type ScratchOff = { slot_number: number; ending_number: string; new_roll_count: number | string; recorded?: boolean }
export type CatalogSlot = { slot_number: number; ticket_price: string; max_ticket_number: number }
export type Comparison = { expected: string; actual: string | null; difference: string | null; status: 'match' | 'mismatch' | 'incomplete' }
export type StoreLocation = { id: number; name: string }
export type Session = { user: { id: number; username: string } | null; stores: StoreLocation[]; csrfToken: string }
export type FieldErrors = Record<string, string>

export const independentFields = [
  ['lottery_terminal_sales', 'Current cumulative lottery terminal sales'],
  ['lottery_terminal_payout', 'Current cumulative lottery terminal payout'],
  ['phone_card_actual_sales', 'Actual phone card sales'],
] as const
export const bodegaFields = [
  ['bodega_net_difference', 'Bodega net difference'],
  ['bodega_lottery_sales', 'Bodega lottery sales'],
  ['bodega_lottery_payout', 'Bodega lottery payout'],
  ['bodega_phone_card_sales', 'Bodega phone card sales'],
  ['bodega_gas_sales', 'Gas sold by Bodega'],
] as const
export const gasFields = [
  ['gas_cash_sales', 'Verifone total cash sales'],
  ['gas_lottery_sales', 'Verifone lottery sales'],
  ['gas_lottery_payout', 'Verifone lottery payout'],
  ['gas_phone_card_sales', 'Verifone phone card sales'],
  ['gas_card_payment_sales', 'Card payment without including fee'],
] as const
export const fields = [...independentFields, ...bodegaFields, ...gasFields]
export type AmountKey = typeof fields[number][0]
export type ItemKey = 'bodega_ai_tickets' | 'tickets' | 'vendor_payouts' | 'safe_drops'
export const bodegaAiTicketGroup = { key: 'bodega_ai_tickets', title: 'Bodega AI tickets', type: 'bodega_ai_ticket' } as const
export const verifoneItemGroups: { key: ItemKey; title: string; type: string }[] = [
  { key: 'tickets', title: 'Verifone tickets', type: 'ticket' },
  { key: 'vendor_payouts', title: 'Verifone vendor payouts', type: 'vendor_payout' },
  { key: 'safe_drops', title: 'Verifone safe drops', type: 'safe_drop' },
]
export const itemGroups: { key: ItemKey; title: string; type: string }[] = [bodegaAiTicketGroup, ...verifoneItemGroups]
export type FormState = Record<AmountKey, string> & {
  report_date: string; close_type: CloseType; close_label: string
  bodega_ai_tickets: LineItem[]; tickets: LineItem[]; vendor_payouts: LineItem[]; safe_drops: LineItem[]; scratch_offs: ScratchOff[]
}
export type Report = {
  id: number; report_date: string; close_type: CloseType; close_label: string; created_at: string
  calculated: {
    inputs: Partial<Record<AmountKey, string | null>> & Partial<Record<ItemKey, LineItem[]>>
    scratch_off: {
      sales: string
      slots?: Record<string, {
        tickets_sold: number; ticket_price: string; sales: string; new_roll_count: number
        starting_number: number | null; ending_number: number | null; ending_exhausted: boolean
      }>
    }
    comparisons: { phone_card_sales: Comparison; lottery_sales: Comparison; lottery_payout: Comparison }
    terminal: {
      cumulative_sales: string; cumulative_payout: string
      previous_cumulative_sales: string; previous_cumulative_payout: string
      shift_sales: string; shift_payout: string
    }
    registers: {
      bodega_net_difference: string
      bodega_ai_ticket_total?: string
      bodega_ai_register_balance?: string
      gas_net_difference: string | null
    }
    normalized_line_items?: { item_type: string; amount: string; description: string }[]
    normalized_scratch_offs?: { slot_number: number; ending_number: number | null; new_roll_count: number }[]
  }
}

export type DailySummary = {
  report_date: string; shift_count: number
  shifts: { id: number; close_label: string; created_at: string; terminal_sales: string; terminal_payout: string; scratch_off_sales: string }[]
  terminal: { final_cumulative_sales: string; final_cumulative_payout: string }
  scratch_off: {
    sales: string; total_new_rolls: number; new_rolls_by_slot: Record<string, number>
    final_state: Record<string, { ending_number: number | null; ending_exhausted: boolean }>
    slots: Record<string, {
      tickets_sold: number; ticket_price: string; sales: string; new_roll_count: number
      starting_number: number | null; ending_number: number | null; ending_exhausted: boolean
    }>
  }
  inputs: Partial<Record<AmountKey, string | null>>
  line_items: Record<ItemKey, { total: string; entries: { report_id: number; shift_name: string; amount: string; description: string }[] }>
  registers: {
    lottery_sales: string; lottery_payout: string; bodega_net_difference: string
    bodega_ai_ticket_total: string; bodega_ai_register_balance: string
    gas_net_difference: string | null
  }
  comparisons: { phone_card_sales: Comparison; lottery_sales: Comparison; lottery_payout: Comparison }
}

export const steps = [
  { label: 'Shift details', fields: ['report_date', 'close_label'] },
  { label: 'Machine totals', fields: independentFields.map(([key]) => key) },
  { label: 'Scratch-off count', fields: ['scratch_offs'] },
  { label: 'Bodega AI', fields: [...bodegaFields.map(([key]) => key), bodegaAiTicketGroup.key] },
  { label: 'Verifone', fields: [...gasFields.map(([key]) => key), ...verifoneItemGroups.map(({ key }) => key)] },
]
export const localDate = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
export const initialScratch = (): ScratchOff[] => Array.from({ length: 20 }, (_, index) => ({ slot_number: index + 1, ending_number: '', new_roll_count: 0 }))
export const initialForm = (): FormState => ({
  report_date: localDate(), close_type: 'shift', close_label: '',
  ...Object.fromEntries(fields.map(([key]) => [key, ''])) as Record<AmountKey, string>,
  bodega_ai_tickets: [], tickets: [], vendor_payouts: [], safe_drops: [], scratch_offs: initialScratch(),
})
export const amountOrZero = (value: string) => /^[+-]?$/.test(value.trim()) ? '0.00' : value
export const money = (value: string | null | undefined) => value == null ? 'Needs entry' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value || 0))

export function displayedBodegaBalance(value: string | null): string {
  if (value == null) return 'Needs entry'
  const numericValue = Number(value)
  if (numericValue > 0) return `+${money(String(numericValue))}`
  return money(String(numericValue))
}

export function displayedVerifoneBalance(value: string | null): string {
  if (value == null) return 'Needs entry'
  return displayedBodegaBalance(String(-Number(value)))
}

export function formFromReport(report: Report): FormState {
  const form = initialForm()
  for (const [key] of fields) form[key] = report.calculated.inputs[key] ?? ''
  for (const { key, type } of itemGroups) {
    form[key] = report.calculated.normalized_line_items
      ? report.calculated.normalized_line_items.filter((item) => item.item_type === type).map(({ amount, description }) => ({ amount, description }))
      : (report.calculated.inputs[key] ?? []).map((item) => ({ ...item }))
  }
  form.scratch_offs = initialScratch().map((row) => {
    const saved = report.calculated.normalized_scratch_offs?.find((item) => item.slot_number === row.slot_number)
    return saved ? { ...row, ending_number: String(saved.ending_number ?? ''), new_roll_count: saved.new_roll_count } : { ...row, recorded: false }
  })
  return { ...form, report_date: report.report_date, close_type: report.close_type, close_label: report.close_label }
}

export function flattenErrors(value: unknown, path = ''): FieldErrors {
  if (typeof value === 'string') return { [path || 'form']: value }
  if (Array.isArray(value) && value.every((item) => typeof item === 'string')) return { [path || 'form']: value.join(' ') }
  if (value && typeof value === 'object') {
    return Object.assign({}, ...Object.entries(value).map(([key, entry]) => flattenErrors(entry, path ? `${path}.${key}` : key)))
  }
  return {}
}

export function errorStep(errors: FieldErrors): number | undefined {
  const indexes = Object.keys(errors).map((path) => steps.findIndex((step) => step.fields.includes(path.split('.')[0]))).filter((index) => index >= 0)
  return indexes.length ? Math.min(...indexes) : undefined
}
