import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {getToolPluginMetadata} from 'openclaw/plugin-sdk/tool-plugin';

const root=dirname(fileURLToPath(import.meta.url));
const temp=mkdtempSync(join(root,'.plugin-test-'));
const launcher=join(temp,'mock-launcher.cjs');
writeFileSync(launcher,`#!/usr/bin/env node
let input='';process.stdin.on('data',d=>input+=d);process.stdin.on('end',()=>{
 const req=JSON.parse(input);
 process.stdout.write(JSON.stringify({ok:true,result:{ready:true,request:req}}));
});\n`,{mode:0o700});
const oldLauncher=process.env.HSR_UI_LAUNCHER;
process.env.HSR_UI_LAUNCHER=launcher;
const {default:entry}=await import('./dist/index.js');
test.after(()=>{
 if(oldLauncher===undefined)delete process.env.HSR_UI_LAUNCHER;
 else process.env.HSR_UI_LAUNCHER=oldLauncher;
 rmSync(temp,{recursive:true,force:true});
});
function factory(plugin){
 let value;plugin.register({pluginConfig:{},registerTool(x){value=x;}});
 return typeof value==='function'?value:value.create;
}
test('schema exposes only bounded semantic actions and explicit output formats',()=>{
 const metadata=getToolPluginMetadata(entry);assert.deepEqual(metadata.tools.map(t=>t.name),['hsr_ui']);
 const schema=metadata.tools[0].parameters;
 assert.equal(schema.additionalProperties,false);assert.equal(schema.properties.x,undefined);
 assert.ok(schema.properties.action.anyOf.some(x=>x.const==='scroll'));
 assert.deepEqual(schema.properties.format.anyOf.map(x=>x.const),['agent','full']);
});
test('sandbox is refused; current invocation, owner and payload reach the launcher',async()=>{
 const create=factory(entry);assert.equal(create({sandboxed:true}),null);
 let checks=0;
 const tool=create({agentId:'test',sessionKey:'test-session',assertInvocationCurrent(){checks++;}});
 const result=await tool.execute('id',{action:'analyze',image:'/example/frame.jpg',format:'full'});
 assert.equal(checks,1);assert.equal(result.details.ok,true);
 assert.deepEqual(result.details.result.request,{action:'analyze',image:'/example/frame.jpg',format:'full',_owner:'test:test-session'});
 assert.deepEqual(JSON.parse(result.content[0].text),result.details);
});
test('cancelled invocation fails before launching',async()=>{
 const tool=factory(entry)({sessionKey:'cancelled'});
 const controller=new AbortController();controller.abort();
 await assert.rejects(tool.execute('id',{action:'status'},controller.signal));
});
test('captured package uses the configured absolute launcher outside capture',async()=>{
 const captured=join(temp,'package-0','node_modules','openclaw-plugin-hsr-ui');
 mkdirSync(join(captured,'dist'),{recursive:true});
 writeFileSync(join(captured,'package.json'),JSON.stringify({type:'module'}));
 copyFileSync(join(root,'dist/index.js'),join(captured,'dist/index.js'));
 const {default:copy}=await import(pathToFileURL(join(captured,'dist/index.js')).href);
 const tool=factory(copy)({sessionKey:'captured-test',agentId:'test'});
 const result=await tool.execute('id',{action:'status'});
 assert.equal(result.details.ok,true);assert.equal(result.details.result.ready,true);
});
test('default launcher is home-relative, never package-relative',async()=>{
 const oldHome=process.env.HOME;
 try {
  process.env.HOME=join(temp,'test-home');delete process.env.HSR_UI_LAUNCHER;
  const canonical=join(process.env.HOME,'.agents/skills/hsr-ui/hsr-ui');
  mkdirSync(dirname(canonical),{recursive:true});copyFileSync(launcher,canonical);
  const {default:copy}=await import(pathToFileURL(join(root,'dist/index.js')).href+'?home-test');
  const result=await factory(copy)({sessionKey:'home-test'}).execute('id',{action:'status'});
  assert.equal(result.details.ok,true);
 } finally {
  if(oldHome===undefined)delete process.env.HOME;else process.env.HOME=oldHome;
  process.env.HSR_UI_LAUNCHER=launcher;
 }
});
