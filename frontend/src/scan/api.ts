import type {
  OpportunityScanResponse,
  ScanJobAccepted,
  ScanRunStatus,
  ScanRunSummary,
  StartScanRequest,
} from './types'

function detailFromErrorPayload(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const record = payload as { detail?: unknown; message?: unknown; error_message?: unknown }
    if (typeof record.detail === 'string') return record.detail
    if (typeof record.message === 'string') return record.message
    if (typeof record.error_message === 'string') return record.error_message
  }
  return fallback
}

export async function listScanRuns(baseUrl: string, limit = 8): Promise<ScanRunSummary[]> {
  const response = await fetch(`${baseUrl}/api/v1/scan/runs?limit=${limit}`)
  if (!response.ok) throw new Error('Failed to load scan history')
  return (await response.json()) as ScanRunSummary[]
}

export async function getScanRun(
  baseUrl: string,
  scanRunId: number,
): Promise<OpportunityScanResponse | ScanRunStatus> {
  const response = await fetch(`${baseUrl}/api/v1/scan/runs/${scanRunId}`)
  if (!response.ok) {
    let detail = 'Failed to load scan run'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as OpportunityScanResponse | ScanRunStatus
}

export function isCompletedScan(
  payload: OpportunityScanResponse | ScanRunStatus,
): payload is OpportunityScanResponse {
  if (!('opportunities' in payload)) return false
  const status = payload.status ?? 'completed'
  return status === 'completed'
}

export async function startScanJob(
  baseUrl: string,
  body: StartScanRequest,
): Promise<ScanJobAccepted> {
  const response = await fetch(`${baseUrl}/api/v1/scan/opportunities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (response.status !== 202) {
    let detail = 'Scan request failed.'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as ScanJobAccepted
}

/** POST scan then poll until completed or failed. */
export async function runScanAndWait(
  baseUrl: string,
  body: StartScanRequest,
  options?: {
    pollMs?: number
    onStatus?: (status: string, scanRunId: number) => void
    signal?: AbortSignal
  },
): Promise<OpportunityScanResponse> {
  const accepted = await startScanJob(baseUrl, body)
  const scanRunId = accepted.scan_run_id
  options?.onStatus?.(accepted.status, scanRunId)

  const pollMs = options?.pollMs ?? 300
  // First status check immediately so a fast job is not delayed by the poll interval.
  for (;;) {
    if (options?.signal?.aborted) {
      throw new Error('Scan cancelled')
    }
    const payload = await getScanRun(baseUrl, scanRunId)
    const status = payload.status ?? 'completed'
    options?.onStatus?.(status, scanRunId)
    if (status === 'queued' || status === 'running') {
      await new Promise((resolve) => window.setTimeout(resolve, pollMs))
      continue
    }
    if (status === 'failed') {
      const failed = payload as ScanRunStatus
      throw new Error(failed.error_message || 'Scan failed')
    }
    if (isCompletedScan(payload)) {
      return payload
    }
    throw new Error('Unexpected scan response')
  }
}

export function readDeepLinkParams(search = window.location.search): {
  view: string | null
  runId: number | null
  symbol: string | null
} {
  const params = new URLSearchParams(search)
  const runRaw = params.get('run')
  const runId = runRaw && /^\d+$/.test(runRaw) ? Number(runRaw) : null
  return {
    view: params.get('view'),
    runId,
    symbol: params.get('symbol'),
  }
}
