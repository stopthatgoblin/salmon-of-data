import tailwindcss from '@tailwindcss/postcss';
import vinext from 'vinext';
import { defineConfig } from 'vite';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
export default defineConfig({
 css: { postcss: { plugins: [tailwindcss()] } },
 plugins: [vinext(),{name:'markdown-posts',configureServer(server){
   server.watcher.add(path.resolve('content/posts'));
   let timer:ReturnType<typeof setTimeout>;
   const rebuild=(file:string)=>{if(!file.includes('/content/posts/')||!file.endsWith('.md'))return;clearTimeout(timer);timer=setTimeout(()=>{try{execFileSync(process.execPath,['scripts/build-posts.mjs'],{stdio:'inherit'});server.ws.send({type:'full-reload'});}catch(error){server.config.logger.error('Blog update failed. Check the Markdown frontmatter.');}},120)};
   server.watcher.on('add',rebuild).on('change',rebuild).on('unlink',rebuild);
 }}],
 server: { host: '127.0.0.1', port: 3100, strictPort: true, watch: { useFsEvents: false, usePolling: true, ignored:['**/data/raw/**'] } }
});
