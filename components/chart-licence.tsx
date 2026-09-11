type Licence={name:string;url:string;credit:string};
const licences:Record<string,Licence>={
 wb:{name:'CC BY 4.0',url:'https://datacatalog.worldbank.org/search/dataset/0038238/commodity-prices-history-and-projections',credit:'World Bank, Commodity Price Data (Pink Sheet)'},
 fao:{name:'CC BY 4.0 + FAO database terms',url:'https://www.fao.org/contact-us/terms/db-terms-of-use/en',credit:'FAO, Food Price Index'},
 ons:{name:'Open Government Licence v3.0',url:'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',credit:'Office for National Statistics · © Crown copyright'},
 noaa:{name:'Public domain · NOAA/NWS terms',url:'https://www.weather.gov/disclaimer',credit:'NOAA Climate Prediction Center, RONI'},
 indeed:{name:'CC BY 4.0',url:'/data/ai/indeed-LICENSE.txt',credit:'Indeed Hiring Lab, Job Postings Tracker'},
 fed:{name:'New York Fed Terms of Use',url:'https://www.newyorkfed.org/privacy/termsofuse.html',credit:'Federal Reserve Bank of New York, The Labor Market for Recent College Graduates'},
 bls:{name:'Public domain · BLS copyright policy',url:'https://www.bls.gov/opub/copyright-information.htm',credit:'US Bureau of Labor Statistics · retrieved via FRED'},
 canada:{name:'Statistics Canada Open Licence',url:'https://www.statcan.gc.ca/en/terms-conditions/open-licence',credit:'Statistics Canada · Job Vacancy and Wage Survey; calculations by Salmon of Data'},
};
export function ChartLicence({tracker,metric}:{tracker:'el-nino'|'ai';metric:string}){
 const key=tracker==='el-nino'?(metric==='enso'?'noaa':metric==='food'?'fao':metric==='retail'?'ons':'wb'):(metric==='recruitment'?'indeed':['graduates','underemployment'].includes(metric)?'fed':metric.startsWith('canada-')?'canada':'bls');
 const l=licences[key];
 return <div className="chart-licence"><p><strong>Data licence:</strong> <a href={l.url} target="_blank" rel="noreferrer">{l.name} ↗</a> · {l.credit}.</p><p>{key==='fed'&&<>© 2026 Federal Reserve Bank of New York. Content from the New York Fed subject to the Terms of Use at newyorkfed.org. </>}Chart, derived measures and illustrative scenarios: Salmon of Data. Source organisations do not endorse this analysis.</p></div>;
}
