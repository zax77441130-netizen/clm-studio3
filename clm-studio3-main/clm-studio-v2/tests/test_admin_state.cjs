const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=[...fs.readFileSync('frontend/admin.html','utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(x=>x[1]).join('\n').replace(/refreshLoginStatus\(\);\s*$/,'');
function setup(fetch){
 const events={},downloads=[],els={};const get=id=>els[id]??=( {textContent:'',addEventListener:(type,fn)=>events[type]=fn} );
 const ctx=vm.createContext({fetch,console,Blob,setTimeout:fn=>fn(),URL:{createObjectURL:blob=>{downloads.push(blob);return 'blob:test'},revokeObjectURL(){}},confirm:()=>false,document:{getElementById:get,createElement:()=>({click(){}})},window:{addEventListener(){},location:{}}});
 vm.runInContext(source,ctx);const run=code=>vm.runInContext(code,ctx);run('DATA={_version:"v1",site:{zh:{studio_name:"draft"}}};collectAllFields=()=>true');return{run,events,downloads};
}
(async()=>{
 let c=setup(async()=>({ok:false,status:409,json:async()=>({detail:'conflict'})}));await c.run('saveAll()');assert.equal(c.run('DIRTY'),true);assert.equal(c.run('DATA.site.zh.studio_name'),'draft');assert.equal(c.run('DATA._version'),'v1');
 c=setup(async()=>{throw Error('connection lost')});await c.run('saveAll()');assert.equal(c.run('DIRTY'),true);assert.equal(c.run('SAVE_IN_PROGRESS'),false);
 let calls=0,resolve;c=setup(()=>{calls++;return new Promise(r=>resolve=r)});const first=c.run('saveAll()');await c.run('saveAll()');assert.equal(calls,1);c.run('DATA.site.zh.studio_name="new typing";markDirty()');resolve({ok:true,status:200,json:async()=>({version:'v2'})});await first;assert.equal(c.run('DIRTY'),true);assert.equal(c.run('DATA.site.zh.studio_name'),'new typing');assert.equal(c.run('DATA._version'),'v2');
 c=setup(()=>{throw Error('should not fetch')});c.run('DIRTY=true');await c.run('loadSite()');assert.equal(c.run('DATA.site.zh.studio_name'),'draft');c.run('downloadDraft()');assert.equal(JSON.parse(await c.downloads[0].text()).site.zh.studio_name,'draft');c.events.input({target:{matches:()=>true}});assert.equal(c.run('EDIT_REVISION'),1);
 console.log('PASS: conflict draft; network uncertainty; duplicate-save guard; in-flight editing; reload cancel; draft download; input tracking (7 checks)');
})().catch(e=>{console.error(e);process.exitCode=1});
