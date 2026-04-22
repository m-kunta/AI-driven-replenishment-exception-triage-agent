// Jest manual mock for remark-gfm.
// The actual plugin is ESM-only and cannot be loaded by Jest's CommonJS
// transformer. Since our react-markdown mock ignores remarkPlugins entirely,
// this just needs to be a valid export that doesn't throw.
const remarkGfm = () => {}
export default remarkGfm
