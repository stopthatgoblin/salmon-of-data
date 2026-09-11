export type Point={date:string;value:number};
export type Paths={low:Point[];medium:Point[];high:Point[]};
export const monthNumber=(date:string)=>{const [y,m]=date.split('-').map(Number);return y*12+m-1};
export const monthDate=(n:number)=>`${Math.floor(n/12)}-${String(n%12+1).padStart(2,'0')}`;
export function interpolate(path:Point[],n:number):number|null {
  if(n<monthNumber(path[0].date)||n>monthNumber(path[path.length-1].date))return null;
  for(let i=0;i<path.length;i++){const p=path[i],x=monthNumber(p.date);if(n===x)return p.value;if(n<x){const prev=path[i-1],a=monthNumber(prev.date);return prev.value+(p.value-prev.value)*(n-a)/(x-a)}}
  return null;
}
export function chartRows(history:Point[],paths:Paths,start:number,end:number,annual=false){
  const observed=new Map(history.map(p=>[monthNumber(p.date),p.value]));
  const rows=[];
  for(let x=start;x<=end;x+=annual?12:1){rows.push({x,date:monthDate(x),actual:observed.get(x)??null,low:interpolate(paths.low,x),medium:interpolate(paths.medium,x),high:interpolate(paths.high,x)})}
  return rows;
}
