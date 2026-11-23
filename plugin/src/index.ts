import { Type } from 'typebox';
import { defineToolPlugin } from 'openclaw/plugin-sdk/tool-plugin';
import { execFile } from 'node:child_process';
import { homedir } from 'node:os';
import { join } from 'node:path';

// OpenClaw captures/relocates this JS package; the Python skill stays installed here.
const launcher = process.env.HSR_UI_LAUNCHER || join(homedir(), '.agents', 'skills', 'hsr-ui', 'hsr-ui');

const parameters = Type.Object({
  action: Type.Union(['status','analyze','observe','click','scroll','release'].map(x => Type.Literal(x))),
  image: Type.Optional(Type.String({description:'Absolute JPEG path for offline analyze only.'})),
  detail: Type.Optional(Type.Union([Type.Literal('navigation'),Type.Literal('content')])),
  format: Type.Optional(Type.Union([Type.Literal('agent'),Type.Literal('full')],{description:'Default agent: compact decision nodes and state. full: original tree, coordinates, OCR/evidence and timings for debugging.'})),
  observationId: Type.Optional(Type.String({description:'Exact current live observationId returned by observe/click.'})),
  ref: Type.Optional(Type.String({description:'Reference from the selected node in that observation. Use scroll for nodes advertising actions:[scroll]; otherwise click. No coordinates.'})),
  dryRun: Type.Optional(Type.Boolean({description:'Recapture and validate node but do not tap.'})),
},{additionalProperties:false});
const description = 'Star Rail visual UI (not native Android AX). Default compact result: page, observationId, live, nodes[{ref,name,effect,selected?,checked?,enabled?,notification?,target_kind?,semantic_status?}], and decision state. A ref denotes a click candidate, not permission; omitted/null enabled means unknown. Coverage is partial. Names include card/task context. format=full returns the original tree, bounds and diagnostics; detail=content adds visible read-only text. analyze reads saved JPEGs (cannot click); observe captures an already unlocked foreground game. scroll uses exact live observationId/ref on actions:[scroll] nodes for a bounded single swipe; click uses exact live observationId/ref, validates current page/selection/appearance, taps once and returns settled plus a fresh observation; re-observe unsettled/stale results, never blindly retry a tap. Inspect effect and resource/claim authorization. No auto unlock, claim or raw coordinates. release stream at task end; video idle=30s, refs expire=90s.';

export default defineToolPlugin({
  id:'hsr-ui', name:'Star Rail Visual UI', description:'Sprite-first local Star Rail semantic observation and clicks.',
  tools: tool => [tool({
    name:'hsr_ui',label:'Star Rail UI',description,parameters,
    factory({toolContext}) {
      if (toolContext.sandboxed) return null;
      const owner = (toolContext.agentId ?? 'main')+':'+(toolContext.sessionKey ?? toolContext.sessionId ?? 'local');
      return {
        name:'hsr_ui',label:'Star Rail UI',description,parameters,executionMode:'sequential',
        async execute(_id,params,signal) {
          signal?.throwIfAborted();
          toolContext.assertInvocationCurrent?.();
          const payload = {...params,_owner:owner};
          const result = await new Promise((resolve,reject) => {
            const child = execFile(launcher,[],
              {signal,timeout:90000,maxBuffer:4*1024*1024},(error,stdout,stderr) => {
                if(error) reject(new Error(String(error)+' '+stderr.slice(-1000)));
                else {try {resolve(JSON.parse(stdout));} catch(e) {reject(e);}}
              });
            child.stdin?.end(JSON.stringify(payload));
          });
          return {content:[{type:'text',text:JSON.stringify(result)}],details:result};
        }
      };
    }
  })]
});
