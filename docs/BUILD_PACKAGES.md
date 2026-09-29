# Project dependencies

`build.zen` is checked as Zen and its supported registration expressions are
executed by the compiler's project driver. `std.build` defines the public types;
`zen_build_plan` evaluates the graph, and `zen_packages` resolves Git sources.
The driver does not yet execute arbitrary Zen build functions.

```zen
Builder, BuildError = std.build
build = (b :: Builder) Res<(), BuildError> {
    audio = b.add("audio", {
        url: "https://github.com/lantos1618/zen-audio.git",
        rev: "fd7cc1ddc87e8a45068bc632fed6b4ba51a52021",
        src: Path("src/audio.zen"),
        libs: [],
        paths: [],
    }).try();
    b.exe("app", {src: Path("src/main.zen"), deps: [audio]}).try()
        .exe("example", {src: Path("src/example.zen"), deps: [audio]}).try();
    Ok(())
}
```

`exe` and `exe_test` return `Res<Builder, BuildError>`. `.try()` propagates a
failed registration before evaluating the next one. Existing standalone calls
remain valid. The evaluator visits each receiver once and retains declaration
order. Duplicate dependency/target names fail before compiling or running.

`add` returns `Res<Dep, BuildError>`. Its package record has five required fields:

- `url`: HTTPS Git URL, or an absolute `file:///` URL for local repositories.
- `rev`: a full lowercase 40-character Git commit ID; branches, tags and short
  hashes are refused. This pin belongs in version control with the manifest.
- `src`: the module entry relative to the package checkout.
- `libs`: system/native library names to link, as with `b.lib`.
- `paths`: library search directories relative to the package checkout.

A project resolves only the packages used by the selected executable/test
entries. Multiple aliases of the same URL and commit share
`build/packages/<commit>`. Cache creation/verification holds a filesystem lock.
Git is invoked with argument vectors, disabled hooks/fsmonitor and no terminal
credential prompt. Dependency `build.zen` files and submodules are not executed
or built automatically. Native binaries and headers still need their normal
platform preparation.

The first build fetches the exact commit; subsequent builds work offline. Each
reuse checks the origin, HEAD commit, Git object integrity, and a clean worktree
(including untracked/ignored files). A changed or incomplete cache is an error,
not a fallback to a moving branch or sibling checkout. Remove that package's
cache directory to fetch it again. Do not edit cached sources. These checks
catch accidental drift; they are not a sandbox against a hostile local user or
package code. Git SHA-1 object IDs are not an independent SHA-256 archive digest.

For active local development, replace a package's `b.add` registration with
`b.lib` and an explicit sibling `Path`; do not silently override a pin. Local
and pinned modules can coexist. Source paths must be relative and cannot contain
`..` components. Package source is trusted build input, just like local source.

The former `Package {url, version, hash}` declaration was a design stub with no
driver implementation. It is replaced by this executable pinned-source API.
Registry discovery, version solving, a separate lockfile, source override flags,
SHA-256 Git repositories, archive downloads and manifest-editing commands remain
unimplemented.

Validation lives in `tests/quality/project_tests.py`: real local Git repositories,
paths with spaces, chain order/error handling, first fetch, offline reuse,
modified/untracked cache refusal, origin/commit mismatch, invalid pins/paths,
missing entries/commits and unused-dependency selection. These are CLI tests,
not a mocked resolver.
