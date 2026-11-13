// Datas chegam em UTC (ISO-8601) e são exibidas no fuso America/Sao_Paulo.
const TZ = 'America/Sao_Paulo'
const dateFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat('pt-BR', {
  timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
})
const intFmt = new Intl.NumberFormat('pt-BR')
const brlFmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

export const UNAVAILABLE = 'indisponível'

export function fmtDate(value) {
  return value ? dateFmt.format(new Date(value)) : '—'
}
export function fmtDateTime(value) {
  return value ? dateTimeFmt.format(new Date(value)) : '—'
}
export function fmtInt(value) {
  return value === null || value === undefined ? UNAVAILABLE : intFmt.format(value)
}
export function fmtNum(value, digits = 2) {
  if (value === null || value === undefined) return UNAVAILABLE
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(value)
}
export function fmtPct(value, digits = 2) {
  if (value === null || value === undefined) return UNAVAILABLE
  return `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(value)}%`
}
export function fmtSignedInt(value) {
  if (value === null || value === undefined) return UNAVAILABLE
  return (value > 0 ? '+' : '') + intFmt.format(value)
}
export function fmtBRL(value, onRequest = false) {
  if (value === null || value === undefined) return onRequest ? 'Sob consulta' : 'Não informado'
  return brlFmt.format(value)
}
export function relative(value) {
  if (!value) return 'nunca'
  const diff = (Date.now() - new Date(value).getTime()) / 1000
  if (diff < 0) {
    const ahead = -diff
    if (ahead < 3600) return `em ${Math.max(1, Math.round(ahead / 60))} min`
    if (ahead < 86400) return `em ${Math.round(ahead / 3600)} h`
    return `em ${Math.round(ahead / 86400)} dia(s)`
  }
  if (diff < 3600) return `há ${Math.max(1, Math.round(diff / 60))} min`
  if (diff < 86400) return `há ${Math.round(diff / 3600)} h`
  return `há ${Math.round(diff / 86400)} dia(s)`
}
export function truncate(text, size = 90) {
  if (!text) return ''
  return text.length > size ? `${text.slice(0, size - 1)}…` : text
}

export const RUN_STATUS = {
  queued: { label: 'Na fila', severity: 'secondary' },
  running: { label: 'Executando', severity: 'info' },
  retrying: { label: 'Aguardando nova tentativa', severity: 'warn' },
  success: { label: 'Sucesso', severity: 'success' },
  partial: { label: 'Parcial', severity: 'warn' },
  failed: { label: 'Falha', severity: 'danger' },
  skipped: { label: 'Ignorada', severity: 'secondary' },
  abandoned: { label: 'Abandonada', severity: 'danger' },
}
export const SOURCE_LABEL = { inventory: 'Estoque', instagram: 'Instagram' }
export const FORMAT_LABEL = {
  imagem: 'Imagem', video: 'Vídeo', reels: 'Reels', carrossel: 'Carrossel', desconhecido: 'Não identificado',
}
export const ERROR_LABEL = {
  login_required: 'Instagram exigiu login',
  private_profile: 'Perfil privado',
  not_found: 'Perfil não encontrado',
  rate_limited: 'Limite de consultas do Instagram',
  blocked: 'Acesso bloqueado',
  connection: 'Falha de conexão',
  provider_unavailable: 'Provedor indisponível',
  fetch: 'Falha ao acessar o site',
  parser: 'Erro ao interpretar o site',
  empty: 'Nenhum veículo extraído',
  broker: 'Fila indisponível',
  unknown: 'Erro desconhecido',
}
export const VEHICLE_STATUS = {
  ativo: { label: 'Ativo', severity: 'success' },
  nao_encontrado: { label: 'Não encontrado na última coleta', severity: 'warn' },
}
