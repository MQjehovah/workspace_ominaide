<template>
  <div ref="wrap" class="entity-graph">
    <svg ref="svg" class="graph-svg" role="img" aria-label="实体关系图" />
    <div v-if="!nodes.length" class="graph-empty">暂无可视化实体</div>
    <div class="graph-hint">
      <span>拖动节点</span>
      <span class="sep">·</span>
      <span>滚轮缩放</span>
      <span class="sep">·</span>
      <span>点击查看详情</span>
    </div>
    <button class="graph-reset" type="button" @click="fitView">重置视图</button>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  drag,
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  select,
  zoom,
  zoomIdentity,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3'

interface GraphNode extends SimulationNodeDatum {
  id: string
  name: string
  type: string
  source_count: number
  degree: number
}

interface GraphLink extends SimulationLinkDatum<GraphNode> {
  source: string | GraphNode
  target: string | GraphNode
  weight: number
  relation?: string
}

const props = defineProps<{
  nodes: Array<{ id: string; name: string; type: string; source_count?: number }>
  links: Array<{ source: string; target: string; weight?: number; relation?: string }>
  selectedId?: string | null
}>()

const emit = defineEmits<{
  select: [id: string]
}>()

const wrap = ref<HTMLDivElement | null>(null)
const svg = ref<SVGSVGElement | null>(null)

let simulation: Simulation<GraphNode, GraphLink> | null = null
let nodeSelection: any = null
let linkSelection: any = null
let rootSelection: any = null
let zoomBehavior: any = null
let width = 800
let height = 420
let resizeObserver: ResizeObserver | null = null
let renderTimer: number | null = null

const TYPE_COLOR: Record<string, string> = {
  person: '#6366f1',
  project: '#10b981',
  term: '#f59e0b',
}
const TYPE_SOFT: Record<string, string> = {
  person: '#c7d2fe',
  project: '#a7f3d0',
  term: '#fde68a',
}

function color(type: string) {
  return TYPE_COLOR[type] || '#94a3b8'
}

function softColor(type: string) {
  return TYPE_SOFT[type] || '#e2e8f0'
}

function radius(node: GraphNode) {
  return Math.min(19, 6 + Math.sqrt(Math.max(0, node.degree)) * 2.6 + Math.min(4, node.source_count || 0))
}

function endpoint(value: string | GraphNode): GraphNode {
  return value as GraphNode
}

function ticked() {
  if (!nodeSelection || !linkSelection) return
  nodeSelection.attr('transform', (d: GraphNode) => `translate(${d.x ?? 0},${d.y ?? 0})`)
  linkSelection
    .attr('x1', (d: GraphLink) => endpoint(d.source).x ?? 0)
    .attr('y1', (d: GraphLink) => endpoint(d.source).y ?? 0)
    .attr('x2', (d: GraphLink) => endpoint(d.target).x ?? 0)
    .attr('y2', (d: GraphLink) => endpoint(d.target).y ?? 0)
}

function render() {
  const svgEl = svg.value
  const wrapEl = wrap.value
  if (!svgEl || !wrapEl) return

  simulation?.stop()
  simulation = null
  const svgSel = select(svgEl)
  svgSel.selectAll('*').remove()

  width = Math.max(280, wrapEl.clientWidth || 800)
  height = Math.max(280, wrapEl.clientHeight || 420)
  svgSel.attr('viewBox', `0 0 ${width} ${height}`)

  const raw = props.nodes || []
  if (!raw.length) return

  const degree = new Map<string, number>()
  for (const l of props.links || []) {
    degree.set(l.source, (degree.get(l.source) || 0) + 1)
    degree.set(l.target, (degree.get(l.target) || 0) + 1)
  }

  const nodes: GraphNode[] = raw.map((n) => ({
    ...n,
    source_count: Number(n.source_count || 0),
    degree: degree.get(n.id) || 0,
  }))
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const links: GraphLink[] = (props.links || [])
    .filter((l) => byId.has(l.source) && byId.has(l.target))
    .map((l) => ({
      source: l.source,
      target: l.target,
      weight: Number(l.weight || 1),
      relation: l.relation,
    }))

  rootSelection = svgSel.append('g')
  zoomBehavior = zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.25, 3.5])
    .on('zoom', (event) => rootSelection.attr('transform', event.transform))
  svgSel.call(zoomBehavior).on('dblclick.zoom', null)

  linkSelection = rootSelection
    .append('g')
    .attr('class', 'graph-links')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', '#cbd5e1')
    .attr('stroke-opacity', 0.5)
    .attr('stroke-width', (d: GraphLink) => Math.min(3.2, 0.9 + d.weight * 0.9))

  nodeSelection = rootSelection
    .append('g')
    .attr('class', 'graph-nodes')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'graph-node')

  nodeSelection
    .append('circle')
    .attr('class', 'node-halo')
    .attr('r', (d: GraphNode) => radius(d) + 5)
    .attr('fill', (d: GraphNode) => softColor(d.type))
    .attr('fill-opacity', 0.18)
    .attr('stroke', 'none')

  nodeSelection
    .append('circle')
    .attr('class', 'node-dot')
    .attr('r', (d: GraphNode) => radius(d))
    .attr('fill', (d: GraphNode) => color(d.type))
    .attr('fill-opacity', 0.92)
    .attr('stroke', (d: GraphNode) => (d.id === props.selectedId ? '#1e3a8a' : '#ffffff'))
    .attr('stroke-width', (d: GraphNode) => (d.id === props.selectedId ? 3 : 2))
    .style('filter', 'drop-shadow(0 4px 8px rgba(15, 23, 42, .22))')

  nodeSelection
    .append('text')
    .text((d: GraphNode) => d.name)
    .attr('text-anchor', 'middle')
    .attr('dy', (d: GraphNode) => radius(d) + 15)
    .attr('font-size', 11)
    .attr('font-weight', 500)
    .attr('fill', '#475569')
    .attr('paint-order', 'stroke')
    .attr('stroke', 'rgba(255, 255, 255, .95)')
    .attr('stroke-width', 3)
    .attr('stroke-linejoin', 'round')
    .style('pointer-events', 'none')

  nodeSelection
    .append('title')
    .text((d: GraphNode) => `${d.name} · ${typeName(d.type)}${d.degree ? ` · ${d.degree} 条关联` : ''}`)

  let dragged = false
  const dragBehavior = drag<SVGGElement, GraphNode>()
    .on('start', (event, d) => {
      dragged = false
      if (!event.active) simulation?.alphaTarget(0.24).restart()
      d.fx = d.x
      d.fy = d.y
    })
    .on('drag', (event, d) => {
      if (Math.abs(event.dx) + Math.abs(event.dy) > 0.8) dragged = true
      d.fx = event.x
      d.fy = event.y
    })
    .on('end', (event, d) => {
      if (!event.active) simulation?.alphaTarget(0)
      d.fx = null
      d.fy = null
      window.setTimeout(() => {
        dragged = false
      }, 0)
    })

  const neighbors = new Map<string, Set<string>>()
  for (const l of links) {
    const a = String(l.source)
    const b = String(l.target)
    if (!neighbors.has(a)) neighbors.set(a, new Set())
    if (!neighbors.has(b)) neighbors.set(b, new Set())
    neighbors.get(a)!.add(b)
    neighbors.get(b)!.add(a)
  }

  nodeSelection
    .call(dragBehavior)
    .on('mouseenter', (_event: MouseEvent, d: GraphNode) => {
      const keep = new Set([d.id, ...(neighbors.get(d.id) || [])])
      nodeSelection.style('opacity', (n: GraphNode) => (keep.has(n.id) ? 1 : 0.16))
      linkSelection.attr('stroke-opacity', (l: GraphLink) =>
        endpoint(l.source).id === d.id || endpoint(l.target).id === d.id ? 0.95 : 0.06)
    })
    .on('mouseleave', () => {
      nodeSelection.style('opacity', 1)
      linkSelection.attr('stroke-opacity', 0.5)
    })
    .on('click', (event: MouseEvent, d: GraphNode) => {
      event.stopPropagation()
      if (dragged) return
      emit('select', d.id)
    })

  simulation = forceSimulation<GraphNode>(nodes)
    .force(
      'link',
      forceLink<GraphNode, GraphLink>(links)
        .id((d) => d.id)
        .distance((d) => 72 + 34 / Math.max(1, d.weight))
        .strength(0.35),
    )
    .force('charge', forceManyBody<GraphNode>().strength(-210))
    .force('center', forceCenter(width / 2, height / 2))
    .force('collision', forceCollide<GraphNode>().radius((d) => radius(d) + 22))
    .on('tick', ticked)

  // Settle once synchronously, then fit the graph to the viewport.
  simulation.stop()
  for (let i = 0; i < 220; i += 1) simulation.tick()
  ticked()
  requestAnimationFrame(fitView)
}

function fitView() {
  const svgEl = svg.value
  if (!svgEl || !rootSelection || !zoomBehavior) return
  const root = rootSelection.node() as SVGGElement | null
  if (!root) return
  const box = root.getBBox()
  if (!box.width || !box.height) return
  const padding = 30
  const scale = Math.max(
    0.25,
    Math.min(1.9, (width - padding * 2) / box.width, (height - padding * 2) / box.height),
  )
  const tx = width / 2 - scale * (box.x + box.width / 2)
  const ty = height / 2 - scale * (box.y + box.height / 2)
  select(svgEl).call(
    zoomBehavior.transform,
    zoomIdentity.translate(tx, ty).scale(scale),
  )
}

function updateSelection() {
  if (!nodeSelection) return
  nodeSelection
    .select('.node-dot')
    .attr('stroke', (d: GraphNode) => (d.id === props.selectedId ? '#1e3a8a' : '#ffffff'))
    .attr('stroke-width', (d: GraphNode) => (d.id === props.selectedId ? 3 : 2))
}

function typeName(type: string) {
  return ({ person: '人物', project: '项目', term: '术语' } as Record<string, string>)[type] || type
}

function scheduleRender() {
  if (renderTimer !== null) window.clearTimeout(renderTimer)
  renderTimer = window.setTimeout(() => {
    renderTimer = null
    render()
  }, 60)
}

watch(() => [props.nodes, props.links], scheduleRender)
watch(() => props.selectedId, updateSelection)

onMounted(() => {
  render()
  if (wrap.value && typeof ResizeObserver !== 'undefined') {
    let lastWidth = wrap.value.clientWidth
    resizeObserver = new ResizeObserver(() => {
      const next = wrap.value?.clientWidth || 0
      if (Math.abs(next - lastWidth) < 2) return
      lastWidth = next
      scheduleRender()
    })
    resizeObserver.observe(wrap.value)
  }
})

onBeforeUnmount(() => {
  if (renderTimer !== null) window.clearTimeout(renderTimer)
  resizeObserver?.disconnect()
  simulation?.stop()
  simulation = null
})

defineExpose({ fitView, reset: fitView })
</script>

<style scoped>
.entity-graph {
  position: relative;
  height: 420px;
  border-radius: 16px;
  border: 1px solid #e6eaf3;
  background-color: #fbfcff;
  background-image:
    radial-gradient(circle at 1px 1px, rgba(148, 163, 184, .28) 1px, transparent 0),
    linear-gradient(180deg, rgba(99, 102, 241, .05), transparent 45%);
  background-size: 18px 18px, 100% 100%;
  overflow: hidden;
}
.graph-svg { width: 100%; height: 100%; display: block; touch-action: none; }
.graph-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: #b0b5bd; font-size: 13px;
}
.graph-hint {
  position: absolute; left: 12px; bottom: 10px;
  display: flex; gap: 5px; align-items: center;
  font-size: 11px; color: #94a3b8;
  background: rgba(255, 255, 255, .82);
  border: 1px solid rgba(226, 232, 240, .9);
  border-radius: 999px; padding: 3px 10px;
  backdrop-filter: blur(6px);
  pointer-events: none;
}
.graph-hint .sep { opacity: .5; }
.graph-reset {
  position: absolute; right: 12px; bottom: 10px;
  font-size: 11px; color: #64748b;
  background: rgba(255, 255, 255, .9);
  border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 4px 10px; cursor: pointer; transition: all .15s;
}
.graph-reset:hover { color: #4f46e5; border-color: #c7d2fe; background: #fff; }
@media (max-width: 760px) {
  .entity-graph { height: 330px; }
  .graph-hint { display: none; }
}
</style>
