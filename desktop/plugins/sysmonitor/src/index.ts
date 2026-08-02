import { execFile } from 'child_process'
import Page from './Page.vue'
import Panel from './Panel.vue'

/**
 * 系统监控 plugin v1.1
 * - CPU / memory (os module, live)
 * - Disk usage per drive (PowerShell Win32_LogicalDisk)
 * - GPU info (nvidia-smi if present, else Win32_VideoController)
 * - Memory cleanup (EmptyWorkingSet) and disk cleanup (temp files)
 */

const REFRESH_INTERVAL = 4000
let ctx: any = null
let timer: any = null
let lastCpu = sampleCpuTimes()
let inFlight = false

interface CpuTimes { idle: number; total: number }

function sampleCpuTimes(): CpuTimes {
  const os = require('os')
  let idle = 0, total = 0
  for (const cpu of os.cpus()) {
    for (const type in cpu.times) total += cpu.times[type]
    idle += cpu.times.idle
  }
  return { idle, total }
}

function cpuPercent(): number {
  const now = sampleCpuTimes()
  const idleDelta = now.idle - lastCpu.idle
  const totalDelta = now.total - lastCpu.total
  lastCpu = now
  if (totalDelta <= 0) return 0
  return Math.round((1 - idleDelta / totalDelta) * 100)
}

function runPs(script: string, timeout = 10000): Promise<string> {
  return new Promise((resolve) => {
    if (inFlight) return resolve('')
    inFlight = true
    const encoded = Buffer.from(script, 'utf16le').toString('base64')
    const child = execFile('powershell', ['-NoProfile', '-EncodedCommand', encoded], { timeout, windowsHide: true }, (err, stdout) => {
      inFlight = false
      if (err) return resolve('')
      resolve(stdout.trim())
    })
    setTimeout(() => { try { child.kill() } catch { /* ignore */ } }, timeout + 2000)
  })
}

function memStats() {
  const os = require('os')
  const total = os.totalmem()
  const free = os.freemem()
  const used = total - free
  return {
    percent: total ? Math.round((used / total) * 100) : 0,
    usedGB: Math.round(used / 1024 / 1024 / 1024 * 10) / 10,
    totalGB: Math.round(total / 1024 / 1024 / 1024 * 10) / 10,
  }
}

const DISK_PS = [
  'Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"',
  '| ForEach-Object { "{0}|{1}|{2}" -f $_.DeviceID, [math]::Round($_.Size/1GB,1), [math]::Round(($_.Size-$_.FreeSpace)/1GB,1) }',
].join(' ')

const GPU_NV_PS = [
  '$x = Get-Command nvidia-smi -ErrorAction SilentlyContinue',
  'if ($x) { nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits | Select-Object -First 1 }',
  'else { Get-CimInstance Win32_VideoController | ForEach-Object { "{0}|{1}" -f $_.Name, [math]::Round(($_.AdapterRAM/1GB),0) } }',
].join('\n')

const MEM_CLEAN_PS = [
  '$OutputEncoding = [System.Text.Encoding]::UTF8;',
  '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;',
  'Add-Type -TypeDefinition \'using System;using System.Runtime.InteropServices;public class M{[DllImport("psapi.dll")] public static extern bool EmptyWorkingSet(IntPtr h);}\'',
  'Get-Process | Where-Object { $_.Id -ne $PID } | ForEach-Object { try { [M]::EmptyWorkingSet($_.Handle) | Out-Null } catch {} }',
  'Write-Output "done"',
].join('\n')

const DISK_CLEAN_PS = [
  '$OutputEncoding = [System.Text.Encoding]::UTF8;',
  '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;',
  '$paths = @($env:TEMP, "C:\\Windows\\Temp", $env:WINDIR + "\\Temp")',
  '$freed = 0',
  'foreach ($p in $paths) { if (Test-Path $p) { $before = 0; $after = 0',
  '  $before = (Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum',
  '  Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue',
  '  $after = (Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum',
  '  $freed += ($before - $after) } }',
  'Write-Output ([math]::Round($freed/1MB,1))',
].join('\n')

async function getStats() {
  const mem = memStats()
  const cpu = cpuPercent()
  const os = require('os')
  const load = os.loadavg()
  const uptime = Math.round(os.uptime())

  let disks: any[] = []
  let gpu: string | null = null
  let gpuUtil: number | null = null
  let gpuMem: string | null = null

  const diskOut = await runPs(DISK_PS)
  if (diskOut) {
    disks = diskOut.split(/\r?\n/).filter(Boolean).map((line: string) => {
      const [drive, total, used] = line.split('|')
      const totalN = parseFloat(total) || 0
      const usedN = parseFloat(used) || 0
      return { drive, total: totalN, used: usedN, free: Math.round((totalN - usedN) * 10) / 10, percent: totalN ? Math.round((usedN / totalN) * 100) : 0 }
    })
  }

  const gpuOut = await runPs(GPU_NV_PS, 8000)
  if (gpuOut) {
    const parts = gpuOut.split(/\r?\n/)[0] || ''
    const segs = parts.split('|')
    if (segs.length >= 5 && !parts.includes('Adapter')) {
      gpu = segs[0].trim()
      gpuUtil = parseInt(segs[1]) || 0
      gpuMem = `${segs[2]}/${segs[3]} MB`
    } else if (segs.length >= 2) {
      gpu = segs[0].trim()
      gpuMem = segs[1] ? `${segs[1]} GB` : null
    }
  }

  return {
    cpu,
    mem,
    load: load[0] !== undefined ? load[0].toFixed(1) : '0',
    uptime: `${Math.floor(uptime / 86400)}天${Math.floor((uptime % 86400) / 3600)}时${Math.floor((uptime % 3600) / 60)}分`,
    platform: os.platform(),
    disks,
    gpu,
    gpuUtil,
    gpuMem,
  }
}

export default {
  panel: Panel,
  page: Page,

  async activate(context: any) {
    ctx = context

    context.registerCommand('getPanelData', async () => {
      try {
        const s = await getStats()
        const diskTotal = s.disks.reduce((a, d) => a + d.total, 0)
        const diskUsed = s.disks.reduce((a, d) => a + d.used, 0)
        const diskPct = diskTotal ? Math.round((diskUsed / diskTotal) * 100) : 0
        const cpuColor = s.cpu > 80 ? '#e11d48' : s.cpu > 50 ? '#f59e0b' : '#10b981'
        return {
          title: '系统监控',
          subtitle: `${s.platform} · 运行 ${s.uptime}`,
          items: [
            { title: 'CPU', subtitle: `${s.cpu}%`, action: undefined },
            { title: '内存', subtitle: `${s.mem.usedGB}/${s.mem.totalGB} GB · ${s.mem.percent}%`, action: undefined },
            { title: '磁盘', subtitle: s.disks.length ? `已用 ${diskPct}%` : '—', action: undefined },
            { title: 'GPU', subtitle: s.gpu ? `${s.gpuUtil ?? '—'}%` : '无', action: undefined },
          ],
          buttons: [{ label: '详情 / 清理', command: 'open' }],
        }
      } catch {
        return { title: '系统监控', subtitle: '不可用', items: [] }
      }
    })

    context.registerCommand('getPageData', async () => {
      try { return { stats: await getStats() } } catch { return { stats: null } }
    })

    context.registerCommand('cleanMemory', async () => {
      const before = memStats().percent
      await runPs(MEM_CLEAN_PS)
      const after = memStats().percent
      context.notification?.show('🧹 内存清理完成', `内存占用 ${before}% → ${after}%`)
      return { success: true, before, after }
    })

    context.registerCommand('cleanDisk', async () => {
      const out = await runPs(DISK_CLEAN_PS, 60000)
      const freed = parseFloat(out) || 0
      context.notification?.show('🧹 磁盘清理完成', freed > 0 ? `释放 ${freed} MB` : '无临时文件可清理')
      return { success: true, freedMB: freed }
    })

    context.registerCommand('open', async () => context.openPage('sysmonitor'))

    timer = setInterval(() => {
      try { context.signal?.('panel:updated') } catch { /* ignore */ }
    }, REFRESH_INTERVAL)
  },

  deactivate() {
    if (timer) { clearInterval(timer); timer = null }
  },
}
