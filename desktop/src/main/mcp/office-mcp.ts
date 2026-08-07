import { readFileSync, readdirSync, statSync, existsSync, writeFileSync, mkdirSync, rmSync, createWriteStream } from 'fs'
import { join, resolve, basename } from 'path'
import { z } from 'zod'
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { open } from 'yauzl'

// eslint-disable-next-line @typescript-eslint/no-var-requires
const archiver = require('archiver')

export const OFFICE_SERVER_ID = 'office'

export interface OfficeClientHandle {
  client: Client
  server: McpServer
  transports: [InMemoryTransport, InMemoryTransport]
}

function truncate(s: string, max = 30000): string {
  if (!s || s.length <= max) return s
  const head = s.slice(0, Math.floor(max * 0.8))
  const tail = s.slice(s.length - Math.floor(max * 0.2))
  return `${head}\n\n…[内容过长已截断,共 ${s.length} 字符]…\n\n${tail}`
}

function xmlDecode(s: string): string {
  return s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&')
}

function xmlEncode(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;')
}

function unzipAll(zipPath: string): Promise<Map<string, Buffer>> {
  return new Promise((resolve2, reject) => {
    const files = new Map<string, Buffer>()
    open(zipPath, { lazyEntries: true }, (err, zipfile) => {
      if (err) return reject(err)
      if (!zipfile) return reject(new Error('无法打开 zip'))
      zipfile.readEntry()
      zipfile.on('entry', entry => {
        if (/\/$/.test(entry.fileName)) { zipfile.readEntry(); return }
        zipfile.openReadStream(entry, (err2, stream) => {
          if (err2) { zipfile.readEntry(); return }
          const chunks: Buffer[] = []
          stream.on('data', c => chunks.push(c))
          stream.on('end', () => {
            files.set(entry.fileName, Buffer.concat(chunks))
            zipfile.readEntry()
          })
        })
      })
      zipfile.on('end', () => resolve2(files))
      zipfile.on('error', e => reject(e))
    })
  })
}

function rezipAll(files: Map<string, Buffer>, outPath: string): Promise<void> {
  return new Promise((resolve2, reject) => {
    const output = createWriteStream(outPath)
    const archive = archiver('zip', { zlib: { level: 9 } })
    output.on('close', () => resolve2())
    archive.on('error', e => reject(e))
    archive.pipe(output)
    for (const [name, buf] of files) {
      archive.append(buf, { name })
    }
    archive.finalize()
  })
}

function extractDocxText(xml: string): string {
  const parts: string[] = []
  const paraRe = /<w:p\b[^>]*>([\s\S]*?)<\/w:p>/g
  let m: RegExpExecArray | null
  while ((m = paraRe.exec(xml))) {
    const para = m[1]
    const texts: string[] = []
    const tRe = /<w:t\b[^>]*>([\s\S]*?)<\/w:t>/g
    let tm: RegExpExecArray | null
    while ((tm = tRe.exec(para))) texts.push(xmlDecode(tm[1]))
    if (texts.length) parts.push(texts.join(''))
  }
  return parts.join('\n')
}

function extractPptxText(xml: string): string {
  const lines: string[] = []
  const paraRe = /<a:p\b[^>]*>([\s\S]*?)<\/a:p>/g
  let m: RegExpExecArray | null
  while ((m = paraRe.exec(xml))) {
    const para = m[1]
    const texts: string[] = []
    const tRe = /<a:t\b[^>]*>([\s\S]*?)<\/a:t>/g
    let tm: RegExpExecArray | null
    while ((tm = tRe.exec(para))) texts.push(xmlDecode(tm[1]))
    if (texts.length) lines.push(texts.join(''))
  }
  return lines.join('\n')
}

async function readOfficeDoc(args: { path: string; maxChars?: number }): Promise<string> {
  const target = resolve(args.path)
  if (!existsSync(target)) return `文件不存在: ${target}`
  const lower = target.toLowerCase()
  if (!/\.(docx|pptx)$/.test(lower)) return '仅支持 .docx / .pptx 文件'
  const files = await unzipAll(target)
  const maxChars = args.maxChars ?? 30000
  if (lower.endsWith('.docx')) {
    const xml = files.get('word/document.xml')
    if (!xml) return '不是有效的 docx 文件'
    return truncate(extractDocxText(xml.toString('utf-8')), maxChars)
  }
  const slideNames = [...files.keys()].filter(n => /^ppt\/slides\/slide\d+\.xml$/.test(n))
    .sort((a, b) => parseInt(a.match(/slide(\d+)/)![1]) - parseInt(b.match(/slide(\d+)/)![1]))
  if (!slideNames.length) return '不是有效的 pptx 文件(无幻灯片)'
  const out: string[] = []
  for (let i = 0; i < slideNames.length; i++) {
    const xml = files.get(slideNames[i])!.toString('utf-8')
    out.push(`--- 第 ${i + 1} 页 ---\n${extractPptxText(xml)}`)
  }
  return truncate(out.join('\n\n'), maxChars)
}

async function editOfficeDoc(args: { path: string; find: string; replace: string; saveAs?: string }): Promise<string> {
  const target = resolve(args.path)
  if (!existsSync(target)) return `文件不存在: ${target}`
  const lower = target.toLowerCase()
  const isDocx = lower.endsWith('.docx')
  const isPptx = lower.endsWith('.pptx')
  if (!isDocx && !isPptx) return '仅支持 .docx / .pptx 文件'
  if (!args.find) return '需要 find 参数'
  const files = await unzipAll(target)
  let targetNames: string[]
  if (isDocx) {
    targetNames = ['word/document.xml']
  } else {
    targetNames = [...files.keys()].filter(n => /^ppt\/slides\/slide\d+\.xml$/.test(n))
  }
  const find = xmlEncode(args.find)
  const replace = xmlEncode(args.replace ?? '')
  const textTag = isDocx ? 'w:t' : 'a:t'
  let totalReplace = 0

  for (const name of targetNames) {
    const raw = files.get(name)
    if (!raw) continue
    let xml = raw.toString('utf-8')
    const tagRe = new RegExp(`<${textTag}\\b[^>]*>([\\s\\S]*?)</${textTag}>`, 'g')
    let count = 0
    xml = xml.replace(tagRe, (whole, inner: string) => {
      const decoded = xmlDecode(inner)
      const next = decoded.split(find).join(replace)
      const n = decoded.split(find).length - 1
      count += n
      if (n) return whole.replace(inner, xmlEncode(next))
      return whole
    })
    if (count) {
      files.set(name, Buffer.from(xml, 'utf-8'))
      totalReplace += count
    }
  }

  if (!totalReplace) return `未找到 "${args.find}" 的任何匹配`
  const outPath = args.saveAs ? resolve(args.saveAs) : target
  await rezipAll(files, outPath)
  return `已完成 ${totalReplace} 处替换${outPath !== target ? `,已另存为 ${outPath}` : ''}`
}

async function createOfficeDoc(args: { path: string; type?: string; content: string; title?: string }): Promise<string> {
  const outPath = resolve(args.path)
  if (!args.content) return '需要 content 内容'
  const ext = (outPath.toLowerCase().match(/\.(docx|pptx)$/) || [])[0]
  const type = args.type?.toLowerCase() || ext?.slice(1) || 'docx'
  if (type !== 'docx' && type !== 'pptx') return '仅支持创建 .docx 或 .pptx'
  const finalPath = ext ? outPath : `${outPath}.${type}`
  if (existsSync(finalPath)) return `文件已存在,请使用 edit_office_doc 编辑: ${finalPath}`
  mkdirSync(join(finalPath, '..'), { recursive: true })

  const files = new Map<string, Buffer>()
  const lines = args.content.replace(/\r\n/g, '\n').split('\n')

  if (type === 'docx') {
    const title = args.title ? xmlEncode(args.title) : ''
    const paragraphs = lines
      .filter(l => l.trim().length > 0)
      .map(l => `<w:p><w:r><w:t>${xmlEncode(l)}</w:t></w:r></w:p>`)
      .join('')
    const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
${title ? `<w:p><w:pPr><w:jc w:val="center"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="36"/></w:rPr><w:t>${title}</w:t></w:r></w:p>` : ''}
${paragraphs}
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>
</w:body>
</w:document>`
    files.set('[Content_Types].xml', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`, 'utf-8'))
    files.set('_rels/.rels', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`, 'utf-8'))
    files.set('word/document.xml', Buffer.from(documentXml, 'utf-8'))
  } else {
    const title = args.title ? xmlEncode(args.title) : ''
    const body = lines
      .filter(l => l.trim().length > 0)
      .map(l => `<a:p><a:r><a:rPr lang="zh-CN" altLang="en-US" dirty="0"/><a:t>${xmlEncode(l)}</a:t></a:r></a:p>`)
      .join('')
    const slideXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:cSld><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
${title ? `<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="914400" y="365760"/><a:ext cx="8229600" cy="900000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="zh-CN" sz="3200" b="1"/><a:t>${title}</a:t></a:r></a:p></p:txBody></p:sp>` : ''}
<p:sp><p:nvSpPr><p:cNvPr id="3" name="Body"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="914400" y="1320000"/><a:ext cx="8229600" cy="5000000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr wrap="none"/><a:lstStyle/>
${body}
</p:txBody></p:sp>
</p:spTree></p:cSld><p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr></p:sld>`
    files.set('[Content_Types].xml', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>`, 'utf-8'))
    files.set('_rels/.rels', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>`, 'utf-8'))
    files.set('ppt/presentation.xml', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
<p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>`, 'utf-8'))
    files.set('ppt/_rels/presentation.xml.rels', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>`, 'utf-8'))
    files.set('ppt/slides/slide1.xml', Buffer.from(slideXml, 'utf-8'))
    files.set('ppt/slides/_rels/slide1.xml.rels', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>`, 'utf-8'))
    files.set('ppt/slideMasters/slideMaster1.xml', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>`, 'utf-8'))
    files.set('ppt/slideMasters/_rels/slideMaster1.xml.rels', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>`, 'utf-8'))
    files.set('ppt/slideLayouts/slideLayout1.xml', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr>
</p:sldLayout>`, 'utf-8'))
    files.set('ppt/slideLayouts/_rels/slideLayout1.xml.rels', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>`, 'utf-8'))
    files.set('ppt/theme/theme1.xml', Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office">
<a:themeElements>
<a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2><a:accent1><a:srgbClr val="4F81BD"/></a:accent1><a:accent2><a:srgbClr val="C0504D"/></a:accent2><a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4><a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6><a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>
<a:fontScheme name="Office"><a:majorFont><a:latin typeface="Cambria"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>
<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>
</a:themeElements>
</a:theme>`, 'utf-8'))
  }

  await rezipAll(files, finalPath)
  return `已创建 ${type === 'docx' ? 'Word' : 'PowerPoint'} 文档: ${finalPath} (${lines.length} 段)`
}

function createOfficeMcpServer(): McpServer {
  const server = new McpServer({ name: 'omniaide-office', version: '1.0.0' })
  server.registerTool(
    'create_office_doc',
    {
      title: '创建 Office 文档',
      description: '创建新的 .docx(Word)或 .pptx(PowerPoint)文件,按行生成段落内容',
      inputSchema: {
        path: z.string().describe('输出文件绝对路径,如 C:\\Users\\me\\Desktop\\报告.docx'),
        content: z.string().describe('文档正文内容,每行一个段落'),
        title: z.string().optional().describe('可选,文档标题(居中加粗显示)'),
        type: z.string().optional().describe('可选,docx 或 pptx;路径含扩展名时自动识别'),
      },
    },
    async (args: any) => {
      const content = await createOfficeDoc(args || {})
      return { content: [{ type: 'text', text: content }] }
    }
  )
  server.registerTool(
    'read_office_doc',
    {
      title: '读取 Office 文档',
      description: '读取 .docx 或 .pptx 文件中的文本内容(无需安装 Office)',
      inputSchema: {
        path: z.string().describe('docx/pptx 文件绝对路径'),
        maxChars: z.number().optional().describe('最多返回字符数,默认 30000'),
      },
    },
    async (args: any) => {
      const content = await readOfficeDoc(args || {})
      return { content: [{ type: 'text', text: content }] }
    }
  )
  server.registerTool(
    'edit_office_doc',
    {
      title: '编辑 Office 文档',
      description: '在 .docx / .pptx 文件中查找并替换文本(可另存为新文件),修改会覆盖原文件',
      inputSchema: {
        path: z.string().describe('docx/pptx 文件绝对路径'),
        find: z.string().describe('要查找的文本(区分大小写)'),
        replace: z.string().optional().describe('替换为的文本'),
        saveAs: z.string().optional().describe('可选,另存为的路径;不填则覆盖原文件'),
      },
    },
    async (args: any) => {
      const content = await editOfficeDoc(args || {})
      return { content: [{ type: 'text', text: content }] }
    }
  )
  return server
}

export async function createOfficeClient(): Promise<OfficeClientHandle> {
  const server = createOfficeMcpServer()
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair()
  const client = new Client({ name: 'omniaide-assistant', version: '1.0.0' })
  await Promise.all([
    client.connect(clientTransport),
    server.connect(serverTransport),
  ])
  return { client, server, transports: [clientTransport, serverTransport] }
}

export async function closeOfficeClient(handle: OfficeClientHandle): Promise<void> {
  try { await handle.client.close() } catch { /* ignore */ }
  try { await handle.server.close() } catch { /* ignore */ }
}
