import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve('dist/client');
const posts=JSON.parse(fs.readFileSync('data/posts.json','utf8'));
const routes=['','trackers/el-nino','trackers/ai','trackers/ai/calendar','dashboards/ni-elections','dashboards/ni-electricity','blog',...posts.map(p=>'blog/'+p.slug)];
for(const route of routes){const file=route?path.join(root,route+'.html'):path.join(root,'index.html');assert.ok(fs.existsSync(file),file);const html=fs.readFileSync(file,'utf8');assert.ok(html.includes('Salmon'),`${route}: content`);assert.ok(!html.includes('Untitled site'),`${route}: title`);for(const m of html.matchAll(/(?:src|href)="(\/[^"#?]*)/g)){const target=m[1];if(target==='/'||target.startsWith('//'))continue;if(target.startsWith('/api/electricity/')){assert.ok(['/api/electricity/snapshot.json','/api/electricity/history.json'].includes(target),`Unknown electricity API link: ${target}`);continue;}const p=path.join(root,target);assert.ok(fs.existsSync(p)||fs.existsSync(path.join(p,'index.html'))||fs.existsSync(p.replace(/\/$/,'')+'.html'),`${route}: missing ${target}`)}console.log('OK /'+route);}
const snapshot=JSON.parse(fs.readFileSync('data/dashboard.json','utf8'));
for(const m of snapshot.metrics){assert.ok(fs.readFileSync(path.join(root,'data',m.id+'.csv'),'utf8').includes(String(m.latest.value)));}
console.log('OK source downloads');

const electricityRoot=path.join(root,'data/ni-electricity');
for(const name of ['snapshot.json','history.json','edition.json'])assert.ok(fs.existsSync(path.join(electricityRoot,name)),`Missing electricity dataset: ${name}`);
const electricityPage=fs.readFileSync(path.join(root,'dashboards/ni-electricity.html'),'utf8');
for(const content of ['Live dashboard','07:00 Europe/London','refresh-health','station-dialog','trend-image-png','trend-image-svg','trend-download','Open Data Licence'])assert.ok(electricityPage.includes(content),`Electricity page missing ${content}`);
assert.ok(!electricityPage.includes('auto-refresh.js'));
assert.ok(fs.readFileSync(path.join(root,'index.html'),'utf8').includes('href="/dashboards/ni-electricity/"'));
console.log('OK electricity route, navigation, downloads and live-update labels');
