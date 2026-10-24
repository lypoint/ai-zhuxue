/** Resolve a BCP-47 device preference without losing supported regional choices. */
export function resolveLocale(value: string, supported: readonly string[]): string {
  const normalized = value.replaceAll('_', '-').toLowerCase();
  const exact = supported.find((tag) => tag.toLowerCase() === normalized);
  if (exact) return exact;
  const parts = normalized.split('-');
  if (parts[0] === 'zh') {
    if (parts.includes('hans')) return 'zh-Hans';
    if (parts.includes('hk')) return 'zh-Hant-HK';
    return parts.some((part) => ['hant', 'tw', 'mo'].includes(part)) ? 'zh-Hant' : 'zh-Hans';
  }
  const base = ({no: 'nb', iw: 'he', in: 'id'} as Record<string, string>)[parts[0]] || parts[0];
  const region = parts.find((part, index) => index > 0 && /^(?:[a-z]{2}|[0-9]{3})$/.test(part));
  const regional = region && supported.find((tag) => {
    const candidate = tag.toLowerCase().split('-');
    return candidate[0] === base && candidate.slice(1).includes(region);
  });
  if (regional) return regional;
  const latinAmerica = ['mx', 'ar', 'bo', 'br', 'bz', 'cl', 'co', 'cr', 'cu', 'do', 'ec', 'gt', 'hn', 'ni', 'pa', 'pe', 'pr', 'py', 'sv', 'uy', 've'];
  if (base === 'es' && parts.some((part) => latinAmerica.includes(part))) return 'es-419';
  return supported.find((tag) => tag === base) || supported.find((tag) => tag.split('-')[0] === base) || 'en';
}
