export function plural(count: number, forms: [string, string, string]) {
  const value = Math.abs(count) % 100
  const last = value % 10
  if (value > 10 && value < 20) return forms[2]
  if (last > 1 && last < 5) return forms[1]
  if (last === 1) return forms[0]
  return forms[2]
}

export function formatCount(count: number) {
  return new Intl.NumberFormat("ru-RU").format(count)
}
