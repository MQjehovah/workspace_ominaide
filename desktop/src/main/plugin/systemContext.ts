import { execFile } from 'child_process'

export interface ActiveWindow {
  name: string
  title: string
}

function run(command: string, args: string[], timeout = 2000): Promise<string> {
  return new Promise((resolve) => {
    execFile(command, args, { timeout, maxBuffer: 512 * 1024 }, (err, stdout) => {
      resolve(err ? '' : String(stdout || '').trim())
    })
  })
}

/** Frontmost application and window title (best effort, no window titles on some Linux WMs). */
export async function getActiveWindow(): Promise<ActiveWindow | null> {
  if (process.platform === 'darwin') {
    const script = [
      'tell application "System Events"',
      '  set frontApp to first application process whose frontmost is true',
      '  set appName to name of frontApp',
      '  set winTitle to ""',
      '  try',
      '    set winTitle to title of front window of frontApp',
      '  end try',
      '  return appName & linefeed & winTitle',
      'end tell',
    ].join('\n')
    const out = await run('osascript', ['-e', script])
    if (!out) return null
    const [name, ...titleParts] = out.split('\n')
    return { name: name.trim(), title: titleParts.join(' ').trim() }
  }

  if (process.platform === 'win32') {
    const script = [
      'Add-Type @\"',
      'using System;',
      'using System.Runtime.InteropServices;',
      'using System.Text;',
      'public class Win32 {',
      '  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();',
      '  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);',
      '  [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);',
      '}',
      '\"@',
      '$h = [Win32]::GetForegroundWindow()',
      '$sb = New-Object System.Text.StringBuilder 512',
      '[void][Win32]::GetWindowText($h, $sb, 512)',
      '$pid2 = 0',
      '[void][Win32]::GetWindowThreadProcessId($h, [ref]$pid2)',
      '$p = Get-Process -Id $pid2 -ErrorAction SilentlyContinue',
      'Write-Output ($p.ProcessName + [Environment]::NewLine + $sb.ToString())',
    ].join('\n')
    const out = await run('powershell', ['-NoProfile', '-Command', script], 4000)
    if (!out) return null
    const [name, ...titleParts] = out.split(/\r?\n/)
    return { name: name.trim(), title: titleParts.join(' ').trim() }
  }

  const windowId = await run('xdotool', ['getactivewindow'], 1500)
  if (!windowId) return null
  const title = await run('xdotool', ['getwindowname', windowId], 1500)
  const pid = await run('xdotool', ['getwindowpid', windowId], 1500)
  let name = ''
  if (pid) {
    const comm = await run('sh', ['-c', `cat /proc/${pid}/comm 2>/dev/null`], 1500)
    name = comm.trim()
  }
  return { name: name || title, title }
}
