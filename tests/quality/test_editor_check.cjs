// Real Node fixture suites exercise the gate without installing editor packages.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const driver = path.join(__dirname, 'editor_check.cjs');
const pass = "require('node:test').test('real assertion', () => {});\n";
const cases = [
  ['passing required suite', pass, {}, 0],
  ['all discovered suites execute', pass, { extra: pass }, 0],
  ['additional failing suite', pass, { extra: "require('node:test').test('fails', () => { throw Error('negative'); });" }, 1],
  ['missing required suite', null, {}, 1],
  ['empty suite', '', {}, 1],
  ['skipped only', "require('node:test').test.skip('skip', () => {});", {}, 1],
  ['todo only', "require('node:test').test.todo('later');", {}, 1],
  ['compile failure', pass, { compile: 'exit 7' }, 7],
  ['compile signal', pass, { compile: 'kill -TERM $$' }, 'failure'],
  ['test process signal', 'process.kill(process.pid, "SIGTERM");', {}, 'failure'],
];

for (const [name, source, options, expected] of cases) {
  test(name, () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'zen-editor-gate-'));
    try {
      fs.mkdirSync(path.join(root, 'test'));
      fs.mkdirSync(path.join(root, 'bin'));
      fs.symlinkSync(process.execPath, path.join(root, 'bin/node'));
      fs.writeFileSync(path.join(root, 'bin/npm'), '#!/bin/sh\n' + (options.compile || 'exit 0') + '\n', { mode: 0o755 });
      if (source !== null) fs.writeFileSync(path.join(root, 'test/source-roots.test.cjs'), source);
      if (options.extra) fs.writeFileSync(path.join(root, 'test/extra.test.cjs'), options.extra);
      const env = { ...process.env, PATH: path.join(root, 'bin') + path.delimiter + process.env.PATH };
      // These are independent child test runs, not children of this Node runner.
      delete env.NODE_TEST_CONTEXT;
      const commands = [[process.execPath, driver]];
      if (process.env.ZEN_EDITOR_BASELINE) commands.push([process.env.PYTHON || 'python3', process.env.ZEN_EDITOR_BASELINE]);
      for (const command of commands) {
        const result = spawnSync(command[0], [...command.slice(1), '--project', root], {
          env, encoding: 'utf8', timeout: 15000,
        });
        assert.ifError(result.error);
        assert.equal(result.signal, null);
        const detail = result.stdout + result.stderr;
        if (expected === 'failure') assert.notEqual(result.status, 0, detail);
        else assert.equal(result.status, expected, detail);
        if (expected === 0) assert.match(detail, new RegExp(`editorcheck: ${options.extra ? 2 : 1} nonempty`));
      }
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });
}
