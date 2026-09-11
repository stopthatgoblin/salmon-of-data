import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import { marked } from 'marked';
const root=path.resolve(import.meta.dirname,'..');
const dir=path.join(root,'content/posts');
const safeUrl=(url)=>/^(https?:\/\/|mailto:|\/(?!\/)|#)/i.test(url);
const esc=(s)=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
marked.use({renderer:{html:({text})=>esc(text),link({href,title,tokens}){const label=this.parser.parseInline(tokens);return safeUrl(href)?`<a href="${esc(href)}"${title?` title="${esc(title)}"`:''}>${label}</a>`:label;},image({href,text}){return safeUrl(href)?`<img src="${esc(href)}" alt="${esc(text)}" loading="lazy" />`:esc(text);}}});
const posts=fs.readdirSync(dir).filter(f=>f.endsWith('.md')).map(file=>{
 const {data,content}=matter(fs.readFileSync(path.join(dir,file),'utf8'));
 if(data.draft===true)return null;
 const slug=file.replace(/\.md$/,'');
 if(!/^[a-z0-9-]+$/.test(slug))throw new Error(`Use lowercase words and hyphens for the filename: ${file}`);
 for(const key of ['title','date','author','excerpt'])if(typeof data[key]!=='string'||!data[key].trim())throw new Error(`${file}: ${key} must be a quoted, non-empty string`);
 if(!/^\d{4}-\d{2}-\d{2}$/.test(data.date)||isNaN(Date.parse(data.date)))throw new Error(`${file}: date must be YYYY-MM-DD`);
 return {slug,title:data.title,date:data.date,author:data.author,excerpt:data.excerpt,tag:typeof data.tag==='string'?data.tag:'Notebook',readingMinutes:Math.max(1,Math.ceil(content.split(/\s+/).length/220)),html:marked.parse(content),markdown:content};
}).filter(Boolean).sort((a,b)=>b.date.localeCompare(a.date)||a.slug.localeCompare(b.slug));
fs.mkdirSync(path.join(root,'data'),{recursive:true});
fs.writeFileSync(path.join(root,'data/posts.json'),JSON.stringify(posts,null,2)+'\n');
console.log(`Prepared ${posts.length} published Markdown post(s).`);

// Keep the downloadable shared calendar in sync with its editable source.
fs.copyFileSync(path.join(root,'data/release-calendar.json'),path.join(root,'public/data/release-calendar.json'));
