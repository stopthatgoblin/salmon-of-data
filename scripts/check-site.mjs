import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve('dist/client');
const posts=JSON.parse(fs.readFileSync('data/posts.json','utf8'));
const routes=['','trackers/el-nino','trackers/ai','trackers/ai/calendar','blog',...posts.map(p=>'blog/'+p.slug)];
for(const route of routes){const file=route?path.join(root,route+'.html'):path.join(root,'index.html');assert.ok(fs.existsSync(file),file);const html=fs.readFileSync(file,'utf8');assert.ok(html.includes('Salmon'),`${route}: content`);assert.ok(!html.includes('Untitled site'),`${route}: title`);for(const m of html.matchAll(/(?:src|href)="(\/[^"#?]*)/g)){const target=m[1];if(target==='/'||target.startsWith('//'))continue;const p=path.join(root,target);assert.ok(fs.existsSync(p)||fs.existsSync(path.join(p,'index.html'))||fs.existsSync(p.replace(/\/$/,'')+'.html'),`${route}: missing ${target}`)}console.log('OK /'+route);}
const snapshot=JSON.parse(fs.readFileSync('data/dashboard.json','utf8'));
for(const m of snapshot.metrics){assert.ok(fs.readFileSync(path.join(root,'data',m.id+'.csv'),'utf8').includes(String(m.latest.value)));}
console.log('OK source downloads');
