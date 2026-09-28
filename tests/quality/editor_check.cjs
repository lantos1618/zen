#!/usr/bin/env node
// Compile the editor and require executed, nonempty lifecycle suites.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

function status(result) {
  if (result.error) {
    console.error(`editorcheck: ${result.error.message}`);
    return 1;
  }
  if (result.signal) return 128 + (os.constants.signals[result.signal] || 1);
  return result.status ?? 1;
}

function check(project) {
  const required = path.join(project, 'test/source-roots.test.cjs');
  if (!fs.existsSync(required) || !fs.statSync(required).isFile()) {
    console.error(`editorcheck: missing required lifecycle suite: ${required}`);
    return 1;
  }
  const compiled = status(spawnSync('npm', ['run', 'compile'], {
    cwd: project, stdio: 'inherit',
  }));
  if (compiled) return compiled;
  const suites = fs.readdirSync(path.join(project, 'test'))
    .filter(name => name.endsWith('.test.cjs')).sort();
  for (const name of suites) {
    const suite = path.join(project, 'test', name);
    // A temporary file keeps verbose test output out of spawnSync's bounded
    // capture buffer while preserving stdout/stderr ordering.
    const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'zen-editor-output-'));
    const output = path.join(temporary, 'tap');
    let fd;
    let result;
    let text;
    try {
      fd = fs.openSync(output, 'w');
      result = spawnSync(process.execPath, ['--test', '--test-reporter=tap', suite], {
        cwd: project, stdio: ['ignore', fd, fd],
      });
      fs.closeSync(fd);
      fd = undefined;
      text = fs.readFileSync(output, 'utf8');
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
      fs.rmSync(temporary, { recursive: true, force: true });
    }
    process.stdout.write(text);
    const exit = status(result);
    if (exit) return exit;
    const synthetic = new Set([suite, name, path.relative(project, suite)]);
    const executed = [...text.matchAll(/^ok \d+ - (.+)$/gm)]
      .some(match => !synthetic.has(match[1]) && !/ # (?:SKIP|TODO)\b/.test(match[1]));
    if (!executed) {
      console.error(`editorcheck: no executed tests in ${suite}`);
      return 1;
    }
  }
  console.log(`editorcheck: ${suites.length} nonempty editor suite(s) passed`);
  return 0;
}

const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--project')) {
  console.error('usage: node editor_check.cjs [--project PATH]');
  process.exitCode = 2;
} else {
  try {
    process.exitCode = check(path.resolve(args[1] || path.join(__dirname, '../../editors/vscode')));
  } catch (error) {
    console.error(`editorcheck: ${error.message}`);
    process.exitCode = 1;
  }
}
