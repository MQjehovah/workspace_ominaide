import './style.css'

export { default as NotesEditor } from './components/TipTapEditor.vue'
export {
  configureNotesEditor,
  getEditorApiBase,
  getEditorToken,
  getNotesEditorConfig,
} from './config'
export type { EditorHttp, NotesEditorConfig } from './config'
