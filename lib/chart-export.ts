// Export the plotted SVG to a high-resolution PNG, composing text directly on
// canvas. No foreignObject, remote images or screenshot service is required.
const WIDTH=1200, MARGIN=40;
function wrapText(ctx:CanvasRenderingContext2D,text:string,width:number){
 const lines:string[]=[];let line='';
 for(const word of text.split(/\s+/)){const next=line?line+' '+word:word;if(line&&ctx.measureText(next).width>width){lines.push(line);line=word;}else line=next;}
 if(line)lines.push(line);return lines;
}
export async function createChartPng(chart:HTMLElement,freezeNote:string):Promise<Blob>{
 await document.fonts.ready;
 const source=chart.querySelector<SVGSVGElement>('svg.recharts-surface');
 if(!source)throw new Error('Chart SVG is unavailable');
 const rect=source.getBoundingClientRect();if(rect.width<=0||rect.height<=0)throw new Error('Chart is not visible');
 const clone=source.cloneNode(true) as SVGSVGElement;
 clone.setAttribute('xmlns','http://www.w3.org/2000/svg');clone.setAttribute('width',String(rect.width));clone.setAttribute('height',String(rect.height));clone.setAttribute('viewBox',`0 0 ${rect.width} ${rect.height}`);
 const original=[source,...source.querySelectorAll('*')],copies=[clone,...clone.querySelectorAll('*')];
 const properties=['fill','fill-opacity','stroke','stroke-width','stroke-dasharray','stroke-opacity','opacity','font-family','font-size','font-weight','font-style','text-anchor','dominant-baseline','visibility'];
 original.forEach((el,i)=>{const style=getComputedStyle(el);for(const name of properties)(copies[i] as SVGElement).style.setProperty(name,style.getPropertyValue(name));});
 clone.querySelectorAll('.recharts-active-dot,.recharts-tooltip-cursor').forEach(el=>el.remove());
 const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml;charset=utf-8'}));
 try{
  const img=new Image();await new Promise<void>((resolve,reject)=>{img.onload=()=>resolve();img.onerror=()=>reject(new Error('SVG rendering failed'));img.src=url;});
  const canvas=document.createElement('canvas');const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Canvas unavailable');
  const title=chart.querySelector('.chart-title')?.textContent?.trim()||'Historical data and projections';
  const subtitle=chart.querySelector('.chart-subtitle')?.textContent?.trim()||'';
  const notes=[chart.querySelector('.chart-caption-text')?.textContent,...Array.from(chart.querySelectorAll('.chart-licence p')).map(p=>p.textContent),freezeNote].filter(Boolean).map(s=>s!.replace(/\s+/g,' ').trim());
  const contentWidth=WIDTH-MARGIN*2;
  ctx.font='30px Georgia';const titleLines=wrapText(ctx,title,contentWidth);
  ctx.font='16px Arial';const subtitleLines=wrapText(ctx,subtitle,contentWidth);
  ctx.font='14px Arial';const noteLines=notes.map(n=>wrapText(ctx,n,contentWidth));
  const graphTop=40+titleLines.length*38+subtitleLines.length*23+55;
  const graphHeight=Math.round(contentWidth*rect.height/rect.width);
  const height=graphTop+graphHeight+24+noteLines.reduce((sum,lines)=>sum+lines.length*20+10,0)+48;
  const ratio=2;canvas.width=WIDTH*ratio;canvas.height=height*ratio;ctx.scale(ratio,ratio);
  ctx.fillStyle='#fffdf8';ctx.fillRect(0,0,WIDTH,height);ctx.textBaseline='top';ctx.fillStyle='#182e32';ctx.font='30px Georgia';
  let y=32;for(const line of titleLines){ctx.fillText(line,MARGIN,y);y+=38;}
  ctx.font='16px Arial';ctx.fillStyle='#5b686a';for(const line of subtitleLines){ctx.fillText(line,MARGIN,y);y+=23;}
  y+=16;let x=MARGIN;
  chart.querySelectorAll('.chart-legend > span').forEach(el=>{const icon=el.querySelector('i');if(!icon)return;const style=getComputedStyle(icon);const label=el.textContent?.trim()||'';ctx.strokeStyle=style.borderTopStyle==='dashed'?style.borderTopColor:(style.backgroundColor==='rgba(0, 0, 0, 0)'?style.borderTopColor:style.backgroundColor);ctx.lineWidth=3;ctx.setLineDash(style.borderTopStyle==='dashed'?[7,4]:[]);ctx.beginPath();ctx.moveTo(x,y+9);ctx.lineTo(x+26,y+9);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#5b686a';ctx.font='14px Arial';ctx.fillText(label,x+35,y);x+=ctx.measureText(label).width+70;});
  ctx.drawImage(img,MARGIN,graphTop,contentWidth,graphHeight);
  y=graphTop+graphHeight+18;ctx.strokeStyle='#cbc9bf';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(MARGIN,y);ctx.lineTo(WIDTH-MARGIN,y);ctx.stroke();y+=15;
  ctx.font='14px Arial';ctx.fillStyle='#5b686a';for(const lines of noteLines){for(const line of lines){ctx.fillText(line,MARGIN,y);y+=20;}y+=10;}
  ctx.font='13px Arial';ctx.fillStyle='#6d7f7a';ctx.textAlign='right';ctx.fillText('SALMONOFDATA.COM',WIDTH-MARGIN,height-30);
  return await new Promise<Blob>((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('PNG encoding failed')),'image/png'));
 }finally{URL.revokeObjectURL(url);}
}
export async function downloadChartPng(chart:HTMLElement,filename:string,freezeNote:string){
 const blob=await createChartPng(chart,freezeNote);const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename+'.png';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
