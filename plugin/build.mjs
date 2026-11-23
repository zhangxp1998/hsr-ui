import fs from 'node:fs';import {stripTypeScriptTypes} from 'node:module';
fs.mkdirSync('dist',{recursive:true});
fs.writeFileSync('dist/index.js',stripTypeScriptTypes(fs.readFileSync('src/index.ts','utf8')));
