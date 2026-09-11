// Stable, readable tick positions. Minimum step preserves meaningful units.
export function niceScale(values:number[],minimumStep=1):{domain:[number,number];ticks:number[]}{
 const lo=Math.min(...values),hi=Math.max(...values);
 const raw=Math.max((hi-lo)/4,minimumStep);
 const power=10**Math.floor(Math.log10(raw));
 const step=Math.max(minimumStep,([1,2,5,10].find(n=>n*power>=raw)??10)*power);
 const min=Math.floor(lo/step)*step,max=Math.ceil(hi/step)*step;
 const ticks=[];for(let v=min;v<=max+step*.01;v+=step)ticks.push(Number(v.toFixed(6)));
 return {domain:[min,max===min?max+step:max],ticks};
}
