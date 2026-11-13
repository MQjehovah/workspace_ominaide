import { execFile } from 'child_process'
import { clipboard } from 'electron'

let lastWarnAt = 0

function warnSlowRead(message: string): void {
  const now = Date.now()
  if (now - lastWarnAt < 60_000) return
  lastWarnAt = now
  console.warn(`[clipboard] ${message}`)
}

/**
 * Read the system clipboard without risking the Electron main process.
 *
 * On macOS NSPasteboard reads can block while another app (Office, remote
 * desktop, etc.) is still producing the pasteboard contents. Doing that on the
 * main thread every 500ms froze the whole app and, with a stuck pasteboard,
 * made clipboard access unusable system-wide. `pbpaste` runs in a separate
 * process and is killed by the timeout instead.
 */
export function readClipboardTextSafe(): Promise<string> {
  if (process.platform === 'darwin') {
    return new Promise((resolve) => {
      execFile(
        '/usr/bin/pbpaste',
        [],
        {
          timeout: 1200,
          maxBuffer: 256 * 1024,
          encoding: 'utf8',
          windowsHide: true,
        },
        (error, stdout) => {
          if (!error) {
            resolve(String(stdout || ''))
            return
          }
          const code = (error as NodeJS.ErrnoException).code
          if (code === 'ENOENT') {
            // Non-standard macOS setup: fall back to Electron.
            try {
              resolve(clipboard.readText())
            } catch {
              resolve('')
            }
            return
          }
          if ((error as any).killed || (error as any).signal) {
            warnSlowRead('pasteboard read timed out; skipped this poll')
          } else if (code !== 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER') {
            warnSlowRead(`pasteboard read failed: ${error.message}`)
          }
          resolve('')
        },
      )
    })
  }
  try {
    return Promise.resolve(clipboard.readText())
  } catch {
    return Promise.resolve('')
  }
}
