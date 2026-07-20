<template>
  <div class="pan-page">
    <!-- Top Bar -->
    <div class="pan-topbar">
      <div class="pan-toolbar">
        <button class="pan-btn" @click="showUpload = true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          上传
        </button>
        <button class="pan-btn" @click="showNewFolder = true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
          新建文件夹
        </button>
        <button class="pan-btn" @click="refresh">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
          刷新
        </button>
        <button class="pan-btn" @click="openSyncPanel">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s1-5 5-8c4-3 9-3 13 0 3 2 5 5 5 8"/><path d="M23 12s-1 5-5 8c-4 3-9 3-13 0-3-2-5-5-5-8"/><polyline points="17 16 23 16 23 22"/><polyline points="7 8 1 8 1 2"/></svg>
          同步
        </button>
        <span class="pan-total">{{ files.length + folders.length }} 项</span>
      </div>
    </div>

    <!-- Breadcrumb -->
    <div class="pan-bread">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      <span class="bc-item" @click="goRoot">全部文件</span>
      <span v-for="(c, i) in breadcrumb" :key="i" class="bc-sep">/</span>
      <span v-for="(c, i) in breadcrumb" :key="'c'+i" class="bc-item" @click="goTo(i)">{{ c }}</span>
    </div>

    <!-- File Grid -->
    <div class="pan-body">
      <div v-if="loading" class="pan-loading">
        <div class="spin"></div>
      </div>
      <template v-else>
        <!-- List View Header -->
        <div class="pan-list-header">
          <span class="lh-name">名称</span>
          <span class="lh-size">大小</span>
          <span class="lh-date">修改时间</span>
          <span class="lh-actions">操作</span>
        </div>

        <div class="pan-list">
          <!-- Folders -->
          <div v-for="f in folders" :key="f.id" class="pan-row" @dblclick="enterFolder(f)">
            <div class="pr-icon" @click="enterFolder(f)">
              <svg class="fi-folder" viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
            </div>
            <div class="pr-name" @click="enterFolder(f)">{{ f.original_name }}</div>
            <div class="pr-size">-</div>
            <div class="pr-date">{{ formatDate(f.updated_at) }}</div>
            <div class="pr-actions" @click.stop>
              <button class="pa-btn" title="重命名" @click="startRename(f)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
              <template v-if="getSyncInfo(f)">
                <button class="pa-btn" :title="getSyncInfo(f).enabled ? '暂停同步' : '恢复同步'" @click="toggleSync(getSyncInfo(f))">
                  <svg v-if="getSyncInfo(f).enabled" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none"/></svg>
                </button>
                <button class="pa-btn danger" title="删除同步" @click="deleteSync(getSyncInfo(f).id)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                </button>
              </template>
              <button v-else class="pa-btn" title="设置同步" @click="setupSync(f)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s1-5 5-8c4-3 9-3 13 0 3 2 5 5 5 8"/><path d="M23 12s-1 5-5 8c-4 3-9 3-13 0-3-2-5-5-5-8"/><polyline points="17 16 23 16 23 22"/><polyline points="7 8 1 8 1 2"/></svg>
              </button>
              <button class="pa-btn danger" title="删除" @click="trashFile(f)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
            </div>
          </div>

          <!-- Files -->
          <div v-for="f in files" :key="f.id" class="pan-row" :class="{ selected: previewFileData?.id === f.id }" @click="previewFile(f)" @dblclick="downloadFile(f)">
            <div class="pr-icon">
              <svg v-if="isImage(f)" class="fi-image" viewBox="0 0 24 24" fill="currentColor"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>
              <svg v-else-if="isAudio(f)" class="fi-audio" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
              <svg v-else-if="isVideo(f)" class="fi-video" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              <svg v-else-if="isPDF(f)" class="fi-pdf" viewBox="0 0 24 24" fill="currentColor"><path d="M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8.5 7.5c0 .83-.67 1.5-1.5 1.5H9v2H7.5V7H10c.83 0 1.5.67 1.5 1.5v1zm5 2c0 .83-.67 1.5-1.5 1.5h-2.5V7H15c.83 0 1.5.67 1.5 1.5v3zm4-3H19v1h1.5V11H19v2h-1.5V7h3v1.5zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"/></svg>
              <svg v-else-if="isCode(f)" class="fi-code" viewBox="0 0 24 24" fill="currentColor"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>
              <svg v-else-if="isArchive(f)" class="fi-zip" viewBox="0 0 24 24" fill="currentColor"><path d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-2 6h-2v2h2v2h-2v2h-2v-2h2v-2h-2v-2h2v-2h-2V8h2v2h2v2z"/></svg>
              <svg v-else class="fi-file" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"/></svg>
            </div>
            <div class="pr-name">
              <span class="pn-text">{{ f.original_name }}</span>
              <span v-if="f.is_favorite" class="pn-fav">⭐</span>
            </div>
            <div class="pr-size">{{ formatSize(f.size) }}</div>
            <div class="pr-date">{{ formatDate(f.updated_at) }}</div>
            <div class="pr-actions" @click.stop>
              <button class="pa-btn" :class="{ active: f.is_favorite }" :title="f.is_favorite ? '取消收藏' : '收藏'" @click="toggleFav(f)">
                <svg width="14" height="14" viewBox="0 0 24 24" :fill="f.is_favorite ? '#FF9800' : 'none'" :stroke="f.is_favorite ? '#FF9800' : 'currentColor'" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              </button>
              <button class="pa-btn" title="下载" @click="downloadFile(f)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              </button>
              <button class="pa-btn" title="移动" @click="startMove(f)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><polyline points="15 19 12 22 9 19"/><polyline points="19 9 22 12 19 15"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/></svg>
              </button>
              <button class="pa-btn" title="重命名" @click="startRename(f)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="pa-btn danger" title="删除" @click="trashFile(f)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </div>

          <!-- Empty -->
          <div v-if="!folders.length && !files.length && !loading" class="pan-empty">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#ddd" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <p>此文件夹为空</p>
          </div>
        </div>
      </template>
    </div>

    <!-- Preview Panel (slide-in) -->
    <div v-if="previewFileData" class="preview-panel">
      <div class="pp-header">
        <span class="pp-title">{{ previewFileData.original_name }}</span>
        <button class="pp-close" @click="closePreview">✕</button>
      </div>
      <div class="pp-body">
        <div v-if="isImage(previewFileData) && previewUrl" class="pp-image-wrap" @mouseup="imgMouseUp" @mouseleave="imgMouseUp">
          <div class="pp-image-toolbar">
            <span class="pp-zoom-label">{{ Math.round(imgZoom * 100) }}%</span>
            <button class="pp-zoom-btn" @click="imgZoom = Math.min(5, +(imgZoom + 0.25).toFixed(2))">+</button>
            <button class="pp-zoom-btn" @click="imgZoom = Math.max(0.25, +(imgZoom - 0.25).toFixed(2))">−</button>
            <button class="pp-zoom-btn" @click="resetImgView">适应</button>
          </div>
          <div class="pp-image-scroll" @wheel.prevent="(e: WheelEvent) => { imgZoom = +Math.max(0.25, Math.min(5, imgZoom - e.deltaY * 0.002)).toFixed(2); imgPan.value = { x: 0, y: 0 }; }" @mousemove="imgMouseMove">
            <img :src="previewUrl" class="pp-image" :style="{ transform: 'scale(' + imgZoom + ') translate(' + imgPan.x + 'px,' + imgPan.y + 'px)', cursor: imgZoom > 1 ? 'grab' : 'default' }" @mousedown="imgMouseDown" @dragstart.prevent />
          </div>
        </div>
        <div v-else-if="isVideo(previewFileData) && previewUrl" class="pp-video-wrap">
          <video :src="previewUrl" controls class="pp-video"></video>
        </div>
        <div v-else-if="isAudio(previewFileData) && previewUrl" class="pp-audio-wrap">
          <div class="pp-audio-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="#E91E63"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
          </div>
          <audio :src="previewUrl" controls class="pp-audio"></audio>
        </div>
        <div v-else-if="isPDF(previewFileData)" class="pp-info" style="justify-content:center;">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="#f44336"><path d="M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8.5 7.5c0 .83-.67 1.5-1.5 1.5H9v2H7.5V7H10c.83 0 1.5.67 1.5 1.5v1zm5 2c0 .83-.67 1.5-1.5 1.5h-2.5V7H15c.83 0 1.5.67 1.5 1.5v3zm4-3H19v1h1.5V11H19v2h-1.5V7h3v1.5zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"/></svg>
          <p style="margin:12px 0 4px;color:#333;font-size:14px;">PDF 文件</p>
          <p style="margin:0 0 12px;color:#999;font-size:12px;">将在外部程序中打开</p>
          <button class="pp-dl-btn" @click="downloadFile(previewFileData, true)">打开 PDF</button>
        </div>
        <div v-else-if="previewUrl === 'text'" class="pp-code-wrap">
          <div class="pp-code-scroll"><pre class="pp-code">{{ codeContent }}</pre></div>
        </div>
        <div v-else class="pp-info">
          <div v-if="!previewUrl" class="pp-no-preview">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="#ddd"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"/></svg>
            <p>无法预览此文件（文件服务可能未配置）</p>
            <button class="pp-dl-btn" @click="downloadFile(previewFileData)">下载文件</button>
          </div>
          <template v-else>
          <div class="pp-info-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="#666"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"/></svg>
          </div>
          <table class="pp-info-table">
            <tbody>
              <tr><td>文件名</td><td>{{ previewFileData.original_name }}</td></tr>
              <tr><td>大小</td><td>{{ formatSize(previewFileData.size) }}</td></tr>
              <tr><td>类型</td><td>{{ previewFileData.mime_type || '未知' }}</td></tr>
              <tr><td>创建时间</td><td>{{ formatDateTime(previewFileData.created_at) }}</td></tr>
              <tr><td>修改时间</td><td>{{ formatDateTime(previewFileData.updated_at) }}</td></tr>
            </tbody>
          </table>
          <button class="pp-dl-btn" @click="downloadFile(previewFileData)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            下载文件
          </button>
          </template>
        </div>
      </div>
    </div>

    <!-- Upload Modal -->
    <div v-if="showUpload" class="modal-overlay" @click.self="showUpload = false">
      <div class="modal-card"><div class="modal-hd"><span>上传文件</span><button class="close-btn" @click="showUpload = false">✕</button></div>
        <div class="modal-body">
          <div class="upload-zone" @dragover.prevent @drop.prevent="handleDrop" @click="fileInput?.click()">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#2196F3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <p>拖拽文件到此处，或点击选择</p>
            <span class="upload-hint">支持所有文件类型</span>
          </div>
          <input ref="fileInput" type="file" multiple style="display:none" @change="handleFileSelect" />
          <div v-if="uploadQueue.length" class="upload-queue">
            <div v-for="(item, i) in uploadQueue" :key="i" class="uq-item">
              <span class="uq-name">{{ item.name }}</span>
              <span class="uq-status" :class="item.status">{{ item.statusText }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- New Folder Modal -->
    <div v-if="showNewFolder" class="modal-overlay" @click.self="showNewFolder = false">
      <div class="modal-card small"><div class="modal-hd"><span>新建文件夹</span><button class="close-btn" @click="showNewFolder = false">✕</button></div>
        <div class="modal-body">
          <input v-model="newFolderName" class="pan-input" placeholder="请输入文件夹名称" @keyup.enter="createFolder" />
          <div class="modal-ft"><button class="pan-btn" @click="showNewFolder = false">取消</button><button class="pan-btn primary" @click="createFolder">确定</button></div>
        </div>
      </div>
    </div>

    <!-- Rename Modal -->
    <div v-if="renameTarget" class="modal-overlay" @click.self="renameTarget = null">
      <div class="modal-card small"><div class="modal-hd"><span>重命名</span><button class="close-btn" @click="renameTarget = null">✕</button></div>
        <div class="modal-body">
          <input v-model="renameText" class="pan-input" placeholder="请输入新名称" @keyup.enter="confirmRename" />
          <div class="modal-ft"><button class="pan-btn" @click="renameTarget = null">取消</button><button class="pan-btn primary" @click="confirmRename">确定</button></div>
        </div>
      </div>
    </div>

    <!-- Move Modal -->
    <div v-if="moveTarget" class="modal-overlay" @click.self="moveTarget = null">
      <div class="modal-card"><div class="modal-hd"><span>移动到</span><button class="close-btn" @click="moveTarget = null">✕</button></div>
        <div class="modal-body">
          <div class="move-bread"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2196F3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg><span class="bc-item" @click="moveBrowseRoot">全部文件</span><span v-for="(c, i) in moveBreadcrumb" :key="i" class="bc-sep">/</span><span v-for="(c, i) in moveBreadcrumb" :key="'mc'+i" class="bc-item" @click="moveBrowseTo(i)">{{ c }}</span></div>
          <div class="move-list"><div v-for="f in moveFolders" :key="f.id" class="mv-item" @click="moveBrowse(f)"><svg width="16" height="16" viewBox="0 0 24 24" fill="#FF9800"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>{{ f.original_name }}</div>
            <div v-if="!moveFolders.length" class="mv-empty">无子文件夹</div>
          </div>
          <div class="modal-ft"><button class="pan-btn" @click="moveTarget = null">取消</button><button class="pan-btn primary" @click="confirmMove">移动到此处</button></div>
        </div>
      </div>
    </div>

    <!-- Sync Panel -->
    <div v-if="showSyncPanel" class="modal-overlay" @click.self="showSyncPanel = false">
      <div class="modal-card">
        <div class="modal-hd"><span>同步文件夹</span><button class="close-btn" @click="showSyncPanel = false">✕</button></div>
        <div class="modal-body">
          <div v-if="syncFolders.length === 0" class="sync-empty">
            <p style="color:#999;text-align:center;padding:40px 0;">暂无同步设置</p>
          </div>
          <div v-for="sf in syncFolders" :key="sf.id" class="sync-item">
            <div class="sync-info">
              <div class="sync-path"><span class="sync-label">服务端:</span> {{ sf.server_path }}</div>
              <div class="sync-path"><span class="sync-label">本地:</span> {{ sf.local_path }}</div>
              <span class="sync-status" :class="sf.enabled ? 'on' : 'off'">{{ sf.enabled ? '同步中' : '已暂停' }}</span>
            </div>
            <div class="sync-item-actions">
              <button class="pa-btn" :title="sf.enabled ? '暂停' : '恢复'" @click="toggleSync(sf)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect v-if="sf.enabled" x="6" y="4" width="4" height="16" rx="1"/><rect v-if="sf.enabled" x="14" y="4" width="4" height="16" rx="1"/><polygon v-else points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none"/></svg>
              </button>
              <button class="pa-btn danger" title="删除" @click="deleteSync(sf.id)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const props = defineProps<{ data?: any; execute?: Function; refresh?: Function }>()

const files = ref<any[]>([])
const folders = ref<any[]>([])
const breadcrumb = ref<string[]>([])
const currentPath = ref('/')
const loading = ref(false)
const showUpload = ref(false)
const fileInput = ref<HTMLInputElement>()
const uploadQueue = ref<any[]>([])
const showNewFolder = ref(false)
const newFolderName = ref('')
const renameTarget = ref<any>(null)
const renameText = ref('')
const moveTarget = ref<any>(null)
const moveFolders = ref<any[]>([])
const moveBreadcrumb = ref<string[]>([])
const movePath = ref('/')
const previewFileData = ref<any>(null)
const previewUrl = ref('')
const codeContent = ref('')
const imgZoom = ref(1)
const imgPan = ref({ x: 0, y: 0 })
let isDragging = false
let dragStart = { x: 0, y: 0, px: 0, py: 0 }
let prevBlobUrl = ''

function imgMouseDown(e: MouseEvent) {
  if (imgZoom.value <= 1) return
  isDragging = true
  dragStart = { x: e.clientX, y: e.clientY, px: imgPan.value.x, py: imgPan.value.y }
}

function imgMouseMove(e: MouseEvent) {
  if (!isDragging) return
  imgPan.value = {
    x: dragStart.px + (e.clientX - dragStart.x) / imgZoom.value,
    y: dragStart.py + (e.clientY - dragStart.y) / imgZoom.value,
  }
}

function imgMouseUp() { isDragging = false }

function resetImgView() {
  imgZoom.value = 1
  imgPan.value = { x: 0, y: 0 }
}

function closePreview() {
  if (prevBlobUrl) { URL.revokeObjectURL(prevBlobUrl); prevBlobUrl = '' }
  previewFileData.value = null
  previewUrl.value = ''
}

// File type helpers
function ext(f: any) { return f.original_name?.toLowerCase().split('.').pop() || '' }
function isImage(f: any) { return f.mime_type?.startsWith('image/') || ['jpg','jpeg','png','gif','webp','bmp','svg','ico'].includes(ext(f)) }
function isAudio(f: any) { return f.mime_type?.startsWith('audio/') || ['mp3','wav','flac','ogg','m4a','wma','aac','opus'].includes(ext(f)) }
function isVideo(f: any) { return f.mime_type?.startsWith('video/') || ['mp4','mkv','webm','avi','mov','wmv','flv','m4v'].includes(ext(f)) }
function isPDF(f: any) { return f.mime_type === 'application/pdf' || ext(f) === 'pdf' }
function isCode(f: any) { return /\.(js|ts|py|vue|jsx|tsx|html|css|json|md|xml|yaml|yml|sh|bat|sql|rs|go|java|c|cpp|h)$/i.test(f.original_name) }
function isText(f: any) { return ['txt','log','csv','env','gitignore','ini','cfg','conf','yaml','yml','toml'].includes(ext(f)) || isCode(f) }
function isArchive(f: any) { return /\.(zip|rar|7z|tar|gz|bz2|xz)$/i.test(f.original_name) }

function formatSize(bytes: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function formatDate(d: string) {
  if (!d) return '-'
  return d.slice(0, 16).replace('T', ' ')
}

function formatDateTime(d: string) {
  if (!d) return '-'
  return d.slice(0, 19).replace('T', ' ')
}

async function loadFiles(path: string) {
  loading.value = true; currentPath.value = path
  breadcrumb.value = path.split('/').filter(Boolean)
  try {
    const res = await window.mqbox?.api.get(`/files?page_size=200&folder_path=${encodeURIComponent(path)}`) || { files: [] }
    folders.value = (res.files || []).filter((f: any) => f.is_folder)
    files.value = (res.files || []).filter((f: any) => !f.is_folder)
  } catch { folders.value = []; files.value = [] }
  loading.value = false
}

async function refresh() { loadFiles(currentPath.value) }
function goRoot() { loadFiles('/') }
function goTo(idx: number) { loadFiles('/' + breadcrumb.value.slice(0, idx + 1).join('/') + '/') }
function enterFolder(f: any) { loadFiles((f.folder_path.replace(/\/+$/, '') || '') + '/' + f.original_name + '/') }

// Preview
async function previewFile(f: any) {
  if (prevBlobUrl) { URL.revokeObjectURL(prevBlobUrl); prevBlobUrl = '' }
  previewFileData.value = f
  previewUrl.value = ''
  codeContent.value = ''
  if (isPDF(f)) {
    previewFileData.value = f
    try {
      const res = await window.mqbox?.api.get(`/files/${f.id}/download-url`) || {}
      if (res?.download_url) window.mqbox?.shell.openUrl(res.download_url, f.original_name)
    } catch {}
    return
  }
  try {
    const res = await window.mqbox?.api.get(`/files/${f.id}/download-url`) || {}
    const url = res.download_url
    if (!url) return
    if (isCode(f) || isText(f)) {
      const resp = await fetch(url)
      codeContent.value = await resp.text()
      previewUrl.value = 'text'
    } else {
      previewUrl.value = url
    }
  } catch {}
}

// Upload
async function handleDrop(e: DragEvent) { if (e.dataTransfer?.files) uploadFiles(Array.from(e.dataTransfer.files)) }
function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) uploadFiles(Array.from(input.files))
  input.value = ''
}

async function uploadFiles(list: File[]) {
  const serverUrl = await window.mqbox?.config.get('serverUrl') || 'http://localhost:8000'
  const token = await window.mqbox?.config.get('token') || ''
  for (const file of list) {
    const item = { name: file.name, status: 'uploading', statusText: '上传中...' }
    uploadQueue.value.push(item)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${serverUrl}/api/files/upload/direct?folder_path=${encodeURIComponent(currentPath.value)}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      if (!res.ok) { item.status = 'error'; item.statusText = '上传失败'; continue }
      item.status = 'done'; item.statusText = '完成'
    } catch { item.status = 'error'; item.statusText = '失败' }
  }
  await loadFiles(currentPath.value)
}

// New Folder
async function createFolder() {
  if (!newFolderName.value.trim()) return
  try {
    await window.mqbox?.api.post('/files/folder', { name: newFolderName.value.trim(), parent_path: currentPath.value })
    newFolderName.value = ''; showNewFolder.value = false; await loadFiles(currentPath.value)
  } catch {}
}

// Rename
function startRename(f: any) { renameTarget.value = f; renameText.value = f.original_name }
async function confirmRename() {
  if (!renameTarget.value || !renameText.value.trim()) return
  try { await window.mqbox?.api.put(`/files/${renameTarget.value.id}/rename`, { new_name: renameText.value.trim() }); renameTarget.value = null; await loadFiles(currentPath.value) } catch {}
}

// Delete
async function trashFile(f: any) {
  if (!confirm(`确定将「${f.original_name}」移入回收站？`)) return
  try { await window.mqbox?.api.delete(`/files/${f.id}`); await loadFiles(currentPath.value) } catch {}
}

// Favorite
async function toggleFav(f: any) {
  try { await window.mqbox?.api.post(`/files/${f.id}/favorite`); await loadFiles(currentPath.value) } catch {}
}

// Download
async function downloadFile(f: any, saveAs = false) {
  try {
    const res = await window.mqbox?.api.get(`/files/${f.id}/download-url`) || {}
    if (res.download_url) {
      if (saveAs) { window.open(res.download_url); return }
      window.mqbox?.shell.openExternal(res.download_url)
    }
  } catch {}
}

// Move
async function startMove(f: any) { moveTarget.value = f; movePath.value = '/'; moveBreadcrumb.value = []; await loadMoveFolders('/') }
async function loadMoveFolders(path: string) {
  try { const res = await window.mqbox?.api.get(`/files?page_size=200&folder_path=${encodeURIComponent(path)}&is_folder=true`) || { files: [] }; moveFolders.value = (res.files || []).filter((f: any) => f.is_folder) } catch { moveFolders.value = [] }
}
function moveBrowseRoot() { movePath.value = '/'; moveBreadcrumb.value = []; loadMoveFolders('/') }
function moveBrowseTo(idx: number) { const p = '/' + moveBreadcrumb.value.slice(0, idx + 1).join('/') + '/'; movePath.value = p; moveBreadcrumb.value = moveBreadcrumb.value.slice(0, idx + 1); loadMoveFolders(p) }
function moveBrowse(f: any) { const p = (f.folder_path.replace(/\/+$/, '') || '') + '/' + f.original_name + '/'; movePath.value = p; moveBreadcrumb.value = p.split('/').filter(Boolean); loadMoveFolders(p) }
async function confirmMove() {
  if (!moveTarget.value) return
  try { await window.mqbox?.api.put(`/files/${moveTarget.value.id}/move`, { new_folder_path: movePath.value }); moveTarget.value = null; await loadFiles(currentPath.value) } catch {}
}

// Sync
const showSyncPanel = ref(false)
const syncFolders = ref<any[]>([])

function getSyncInfo(folder: any) {
  const folderPath = (folder.folder_path?.replace(/\/+$/, '') || '') + '/' + folder.original_name + '/'
  return syncFolders.value.find((s: any) => s.server_path === folderPath)
}

function openSyncPanel() {
  showSyncPanel.value = true
  loadSyncFolders()
}

async function loadSyncFolders() {
  try {
    const res = await window.mqbox?.api.get('/sync/folders')
    syncFolders.value = res?.folders || []
  } catch { syncFolders.value = [] }
}

async function setupSync(folder: any) {
  const localPath = await window.mqbox?.dialog.selectFolder()
  if (!localPath) return
  const serverPath = (folder.folder_path?.replace(/\/+$/, '') || '') + '/' + folder.original_name + '/'
  await window.mqbox?.api.post('/sync/folders', { server_path: serverPath, local_path: localPath })
  await loadSyncFolders()
  window.mqbox?.sync.restart()
}

async function toggleSync(sf: any) {
  try { await window.mqbox?.api.put(`/sync/folders/${sf.id}`, { enabled: !sf.enabled }); await loadSyncFolders(); window.mqbox?.sync.restart() } catch {}
}

async function deleteSync(id: number) {
  if (!confirm('确定删除此同步？')) return
  try { await window.mqbox?.api.delete(`/sync/folders/${id}`); await loadSyncFolders(); window.mqbox?.sync.restart() } catch {}
}

onMounted(() => loadFiles('/'))
</script>

<style scoped>
.pan-page { height:100vh; display:flex; flex-direction:column; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f5f6fa; color:#333; }

/* Top Bar */
.pan-topbar { background:#fff; border-bottom:1px solid #e8e8e8; padding:10px 24px; flex-shrink:0; }
.pan-toolbar { display:flex; align-items:center; gap:8px; }
.pan-btn { height:34px; border-radius:8px; border:1px solid #ddd; background:#fff; cursor:pointer; display:inline-flex; align-items:center; gap:6px; padding:0 14px; font-size:13px; color:#555; white-space:nowrap; transition:all 0.15s; }
.pan-btn:hover { border-color:#2196F3; color:#2196F3; background:#f0f8ff; }
.pan-btn.primary { background:#2196F3; color:#fff; border-color:#2196F3; }
.pan-btn.primary:hover { background:#1976D2; }
.pan-total { margin-left:auto; font-size:12px; color:#999; }

/* Breadcrumb */
.pan-bread { display:flex; align-items:center; gap:4px; padding:10px 24px; font-size:13px; background:#fff; border-bottom:1px solid #f0f0f0; flex-shrink:0; }
.bc-item { cursor:pointer; color:#2196F3; }
.bc-item:hover { color:#1565C0; }
.bc-sep { color:#ccc; }

/* List */
.pan-body { flex:1; overflow-y:auto; padding:0 24px 24px; }
.pan-loading { display:flex; align-items:center; justify-content:center; height:200px; }
.spin { width:24px; height:24px; border:2px solid #e0e0e0; border-top-color:#2196F3; border-radius:50%; animation:spin 0.6s linear infinite; }
@keyframes spin { to { transform:rotate(360deg) } }

.pan-list-header { display:flex; align-items:center; padding:10px 12px; font-size:12px; color:#999; border-bottom:1px solid #eee; background:#fafafa; border-radius:8px 8px 0 0; margin-top:12px; }
.lh-name { flex:1; min-width:0; }
.lh-size { width:80px; text-align:right; }
.lh-date { width:150px; text-align:right; }
.lh-actions { width:160px; text-align:right; }

.pan-list { }
.pan-row { display:flex; align-items:center; padding:10px 12px; font-size:13px; border-bottom:1px solid #f0f0f0; cursor:pointer; transition:background 0.1s; border-radius:4px; }
.pan-row:hover { background:#f0f8ff; }
.pan-row.selected { background:#e3f2fd; }

.pr-icon { width:36px; flex-shrink:0; display:flex; align-items:center; justify-content:center; }
.pr-icon svg { width:20px; height:20px; }
.fi-folder { color:#FF9800; }
.fi-image { color:#4CAF50; }
.fi-audio { color:#E91E63; }
.fi-video { color:#9C27B0; }
.fi-pdf { color:#f44336; }
.fi-code { color:#2196F3; }
.fi-zip { color:#FF9800; }
.fi-file { color:#78909C; }

.pr-name { flex:1; min-width:0; display:flex; align-items:center; gap:4px; }
.pn-text { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pn-fav { font-size:12px; flex-shrink:0; }

.pr-size { width:80px; text-align:right; color:#999; font-size:12px; white-space:nowrap; }
.pr-date { width:150px; text-align:right; color:#999; font-size:12px; white-space:nowrap; }
.pr-actions { width:160px; text-align:right; display:flex; gap:2px; justify-content:flex-end; opacity:0; transition:opacity 0.15s; }
.pan-row:hover .pr-actions { opacity:1; }
.pa-btn { width:28px; height:28px; border-radius:6px; border:none; background:transparent; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; color:#999; transition:all 0.12s; }
.pa-btn:hover { background:#e3f2fd; color:#2196F3; }
.pa-btn.danger:hover { background:#fce4ec; color:#c62828; }
.pa-btn.active { color:#FF9800; }

.pan-empty { grid-column:1/-1; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:80px 20px; color:#ccc; gap:12px; }
.pan-empty p { margin:0; font-size:14px; }

/* Preview Panel */
.preview-panel { position:fixed; top:0; right:0; width:420px; height:100vh; background:#fff; box-shadow:-4px 0 24px rgba(0,0,0,0.1); z-index:999; display:flex; flex-direction:column; animation:slideIn 0.2s ease; }
@keyframes slideIn { from { transform:translateX(100%) } to { transform:translateX(0) } }
.pp-header { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #e8e8e8; }
.pp-title { font-size:14px; font-weight:600; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.pp-close { border:none; background:transparent; cursor:pointer; font-size:18px; color:#999; padding:4px; }
.pp-close:hover { color:#333; }
.pp-body { flex:1; padding:20px; display:flex; flex-direction:column; min-height:0; overflow:hidden; }

.pp-image-wrap { display:flex; flex-direction:column; height:100%; }
.pp-image-toolbar { display:flex; align-items:center; gap:6px; padding-bottom:8px; flex-shrink:0; }
.pp-zoom-label { font-size:12px; color:#999; min-width:36px; }
.pp-zoom-btn { height:26px; border-radius:6px; border:1px solid #ddd; background:#fff; cursor:pointer; padding:0 10px; font-size:11px; color:#555; }
.pp-zoom-btn:hover { border-color:#2196F3; color:#2196F3; }
.pp-image-scroll { flex:1; overflow:auto; display:flex; align-items:center; justify-content:center; cursor:grab; }
.pp-image { max-width:100%; max-height:100%; border-radius:8px; box-shadow:0 2px 12px rgba(0,0,0,0.1); transform-origin:center; transition:transform 0.1s; }

.pp-video-wrap { display:flex; align-items:center; justify-content:center; height:100%; }
.pp-video { max-width:100%; max-height:calc(100vh - 120px); border-radius:8px; }

.pp-audio-wrap { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; gap:20px; }
.pp-audio-icon { }
.pp-audio { width:100%; }

.pp-pdf-wrap { height:100%; display:flex; flex-direction:column; }
.pp-pdf-toolbar { display:flex; align-items:center; justify-content:space-between; padding-bottom:8px; flex-shrink:0; font-size:13px; color:#666; }
.pp-pdf { flex:1; width:100%; border:none; border-radius:8px; min-height:0; }

.pp-info { display:flex; flex-direction:column; align-items:center; gap:16px; flex-shrink:0; }
.pp-info-icon { }
.pp-info-table { width:100%; border-collapse:collapse; }
.pp-info-table td { padding:8px 0; font-size:13px; border-bottom:1px solid #f0f0f0; }
.pp-info-table td:first-child { color:#999; width:80px; }

.pp-code-wrap { flex:1; overflow:hidden; min-height:0; }
.pp-code-scroll { height:100%; overflow:auto; background:#1e1e1e; border-radius:8px; padding:16px; }
.pp-code { margin:0; font-size:12px; font-family:'Cascadia Code','Fira Code','JetBrains Mono',monospace; color:#d4d4d4; line-height:1.6; white-space:pre; min-width:100%; }

.pp-dl-btn { height:38px; border-radius:8px; border:none; background:#2196F3; color:#fff; cursor:pointer; display:inline-flex; align-items:center; gap:6px; padding:0 20px; font-size:13px; }
.pp-dl-btn:hover { background:#1976D2; }

/* Modal */
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.35); display:flex; align-items:center; justify-content:center; z-index:1000; backdrop-filter:blur(2px); }
.modal-card { background:#fff; border-radius:14px; box-shadow:0 8px 32px rgba(0,0,0,0.2); width:480px; max-height:80vh; display:flex; flex-direction:column; overflow:hidden; }
.modal-card.small { width:380px; }
.modal-hd { display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #e8e8e8; font-weight:600; font-size:14px; -webkit-app-region:drag; }
.close-btn { border:none; background:transparent; cursor:pointer; font-size:16px; color:#999; -webkit-app-region:no-drag; }
.close-btn:hover { color:#333; }
.modal-body { padding:20px; overflow-y:auto; flex:1; }
.modal-ft { display:flex; gap:8px; justify-content:flex-end; margin-top:16px; }

/* Upload */
.upload-zone { border:2px dashed #b0d4f1; border-radius:12px; padding:48px 20px; text-align:center; cursor:pointer; background:#f5fbff; transition:all 0.2s; }
.upload-zone:hover { border-color:#2196F3; background:#e3f2fd; }
.upload-zone p { margin:8px 0 4px; font-size:14px; color:#333; }
.upload-hint { font-size:12px; color:#999; }
.upload-queue { margin-top:16px; }
.uq-item { display:flex; align-items:center; gap:8px; padding:8px 0; font-size:13px; border-bottom:1px solid #f0f0f0; }
.uq-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#333; }
.uq-status { font-size:11px; padding:2px 10px; border-radius:4px; }
.uq-status.uploading { background:#fff3e0; color:#e65100; }
.uq-status.done { background:#e8f5e9; color:#2e7d32; }
.uq-status.error { background:#fce4ec; color:#c62828; }

/* Move */
.move-bread { display:flex; align-items:center; gap:4px; margin-bottom:12px; font-size:13px; }
.move-list { max-height:200px; overflow-y:auto; border:1px solid #eee; border-radius:8px; padding:4px; }
.mv-item { display:flex; align-items:center; gap:8px; padding:8px 10px; border-radius:6px; cursor:pointer; font-size:13px; color:#333; }
.mv-item:hover { background:#f0f8ff; }
.mv-empty { text-align:center; padding:20px; color:#ccc; font-size:12px; }

/* Input */
.pan-input { width:100%; height:38px; border-radius:8px; border:1px solid #d0d0d0; padding:0 12px; font-size:13px; outline:none; box-sizing:border-box; }
.pan-input:focus { border-color:#2196F3; }

/* Sync */
.sync-empty { }
.sync-item { display:flex; align-items:center; gap:12px; padding:12px 0; border-bottom:1px solid #f0f0f0; }
.sync-info { flex:1; }
.sync-path { font-size:12px; color:#333; margin-bottom:2px; }
.sync-label { color:#999; }
.sync-status { font-size:11px; padding:2px 10px; border-radius:4px; }
.sync-status.on { background:#e8f5e9; color:#2e7d32; }
.sync-status.off { background:#f5f5f5; color:#999; }
.sync-item-actions { display:flex; align-items:center; gap:4px; }

::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:#ddd; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#bbb; }
</style>
