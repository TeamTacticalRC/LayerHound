async function req(path,options={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...options});if(!r.ok){let m=`API error ${r.status}`;try{m=(await r.json()).detail||m}catch{}throw Error(m)}return r.json()}
export const getSystem=()=>req('/api/system');
export const getPrinters=()=>req('/api/printers');
export const createPrinter=p=>req('/api/printers',{method:'POST',body:JSON.stringify(p)});
export const deletePrinter=id=>req(`/api/printers/${id}`,{method:'DELETE'});
export const testPrinter=id=>req(`/api/printers/${id}/test`,{method:'POST'});
export const updatePrinter=(id,p)=>req(`/api/printers/${id}`,{method:'PUT',body:JSON.stringify(p)});
export const reorderPrinters=ids=>req('/api/printers/order',{method:'PUT',body:JSON.stringify({ids})});
export const getServer=()=>req('/api/server');
export const getServerHistory=()=>req('/api/server/history');
