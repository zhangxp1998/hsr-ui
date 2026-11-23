# OpenClaw tool plugin

Build with Node.js 24+ and the OpenClaw SDK peer dependency:

```sh
npm ci
npm run build
npm test
```

Load this `plugin/` directory using your existing OpenClaw plugin installation
workflow. Merge the path into existing configuration; do not replace unrelated
plugin settings. The extension entry is `dist/index.js` and the tool is `hsr_ui`.

Set `HSR_UI_LAUNCHER` in the Gateway's environment to the **absolute** executable
path of `hsr-ui`. Without an override it resolves to
`~/.agents/skills/hsr-ui/hsr-ui`. It deliberately does not resolve relative to
`import.meta.url`: OpenClaw captures/relocates the JS package, which previously
caused ENOENT. Ensure the Gateway also receives the device/resource configuration.

The default compact JSON and explicit `format:full` use the same Python service.
Owner is derived from the agent/session; sandboxed factories refuse device access.
Tests exercise metadata, subprocess transport, cancellation and relocated-package
launching with a temporary mock executable, not the installed device service.

An already-loaded old plugin snapshot must be refreshed through the normal
authorized runtime lifecycle. Do not patch managed capture directories or loop
on reload failures; the direct CLI remains available independently.
