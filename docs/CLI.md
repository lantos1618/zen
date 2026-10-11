# Command lines

## The `zen` command

| command | what it does |
|---|---|
| `zen init [DIR]` | write `build.zen`, `src/main.zen` and `.gitignore`; never overwrites |
| `zen build [PROJECT]` | build every executable target `build.zen` declares, or the named one |
| `zen run [TARGET] [-- ARGS...]` | build one executable target and run it with `ARGS` |
| `zen test [PROJECT] [TARGET] [-- ARGS...]` | build every test target, then run each |
| `zen check ROOT` | type-check a compilation root without writing anything |
| `zen build ROOT --emit-c [-o FILE]` | emit C, or JavaScript or assembly with `--backend`, from a compilation root |
| `zen fmt [--check] FILE...` | format Zen source |
| `zen lsp [REQUESTS REPLIES]` | language server over stdio, or over two files |
| `zen help [COMMAND]` | help for zen or one command |

The `zen` command line is declared as types (`src/zen/zen_cli.zen`), one
struct per command, and parsed as the next section describes.
`zen help run`, `zen -h run` and `zen run --help` print the same help. A
command line that does not parse prints what was wrong and the help of the
command it addressed, on standard error, and exits 2:

```text
$ zen run --bogus
zen: unknown option `--bogus` for `zen run`

Build and run an executable target

Usage: zen run [OPTIONS] [TARGET] [-- <ARGS>...]
...
```

A project command's first word is a project when it names a directory holding
`build.zen`, and a target of `./build.zen` otherwise. `zen run` needs a target
name when `build.zen` declares several executables; naming one that does not
exist lists the ones that do.

`build`, `run` and `test` share the build options:

| option | meaning |
|---|---|
| `--release` | the same as `--mode release` |
| `--mode debug\|release\|small` | the build mode; `debug` when not given |
| `-v`, `--verbose` | print each phase and command, with elapsed milliseconds, on stderr |
| `--cc CC` | the C compiler: `clang`, `gcc`, `tcc`, a path, or command words such as `ccache clang`; defaults to `CC` |

`zen build --target TRIPLE` builds for another platform (`x86_64-linux`,
`aarch64-linux`, `arm64-darwin`, `x86_64-darwin`) with clang. The environment
variables `zen help` lists are:

| variable | meaning |
|---|---|
| `ZEN_STD` | standard library root; default: the `src/` beside the `zen` executable |
| `CC`, `CFLAGS` | C compiler and extra flags for native targets |
| `ZEN_BUILD_DIR` | directory for generated files; default `build` |
| `ZEN_BUILD_OUTPUT` | executable path for the one selected target |
| `ZEN_SYMBOL_MAP` | also write the generated symbol map to this path |

`zen test --seeds N` runs each test target N times, under
`ZEN_ACTOR_SEED=1` to `N`, discarding the output of passing runs; at a
target's first failing seed it prints that run's output and the command that
replays it, then goes on to the next target. `--faults K` adds
`ZEN_ACTOR_FAULTS=K` to those runs (seeded faults, see
[ACTOR_RUNTIME.md](ACTOR_RUNTIME.md)); it needs `--seeds`.

```text
$ zen test --seeds 1000 --faults 50
ok ledger (1000 seeds)
not ok chat_server (seed 417, exit 3)
...the failing run's output...
  rerun: ZEN_ACTOR_SEED=417 ZEN_ACTOR_FAULTS=50 bin/chat_server
zen test: 1 passed, 1 failed (1417 runs)
```

The modes, the toolchain fields of `build.zen` and build reuse are described
under "How the compiler gets built" in [DESIGN.md](DESIGN.md).

## `std.cli`: command lines from types

A program declares its command line as types, and `parse<T>` reads argv into
a `T`. A struct that implements `Cli` is one command: each field is one
argument, and the field's type decides what kind. An enum that implements
`Cli` is a set of subcommands, one per variant.

```zen
{ Cli, Spec, parse } = std.cli

Mode = { Debug | Release | Small }

BuildArgs = {
    verbose :: bool = false,           // -v, --verbose
    jobs    :: u32 = 2,                // --jobs <N>, a u32
    mode    :: Mode = Mode.Debug,      // --mode <MODE>: debug, release or small
    define  :: Vec<str>,               // -D, --define <NAME>, repeatable
    out     :: Res<Path>,              // --out <OUT>, optional
    input   : Path,                    // <INPUT>, positional and required
}

BuildArgs.impl(Cli, {
    about: "Build one input",
    verbose: Spec(short: 'v', help: "Print more detail"),
    jobs: Spec(value: "N", help: "Worker count", env: "TOOL_JOBS"),
    mode: Spec(help: "Build mode"),
    define: Spec(short: 'D', value: "NAME", help: "Add a definition"),
})

Cmd = { Build: BuildArgs | Run: RunArgs | Init }
Cmd.impl(Cli, { name: "tool", about: "Build and run things", version: "1.0.0" })

main = (env: Env) Res<i32, AllocError> {
    a ::= env.mem.alloc();
    parse<Cmd>(env, a).match({
        Err(exit) => Ok(exit.status),
        Ok(cmd)   => cmd.match({
            Build(args) => build(env, a, args),
            Run(args)   => run(env, a, args),
            Init        => init(env, a),
        }),
    })
}
```

**The field's declaration decides its argument.** A field declared `::` is
named on the command line, `--` and the field's name with `_` spelled `-`
(`emit_c_dir` is `--emit-c-dir`). A field declared `:` is positional, in
declaration order, and help names it by the field's name in capitals. The
field's type decides the rest:

| field type | argument |
|---|---|
| `bool` | a switch; `::` only |
| `str`, `Path` | one value |
| `u8` `u16` `u32` `u64` `usize` `i8` `i16` `i32` `i64` | one value, refused outside the type's range |
| an enum whose variants carry nothing | one of its variants' names, in kebab case (`VeryLoud` is `very-loud`) |
| `Res<T>` of any of those | optional: an omitted argument is `None` |
| `Vec<str>` | `::`: repeatable; `:`: one or more words; with `trailing: true`, the words after `--` |

A `::` field with a default is optional and takes the default when the
command line and its variable omit it; help shows a default written as a
literal or as a variant. A `::` field with no default that is not a `bool`,
`Res` or `Vec` is a required option. A `:` field cannot have a default (a
struct body reads `name: T = value` as a constant), so a positional is
required unless it is a `Res<T>`. Any other field type is a compile error at
the field, naming these shapes.

**The impl is the table.** It binds the command's settings, each a `str`:
`name` (the program's name, otherwise argv[0]'s file name), `about`, `note`
(text after the generated help) and `version` (adds `-V`, `--version`). It
binds a `Spec` under the name of any field, or of any variant of an enum,
setting what the type leaves open: `help`, `short`, `value` (the value's name
in help, or a positional's), `env`, `hidden` and `trailing`. The compiler
checks the table: an entry that names no field, variant or setting, a setting
that is not a `str`, a field entry that is not a `Spec`, and a `Spec` that
sets `kind`, `choices`, `min`, `max`, `default`, `required` or `many` are
errors at that entry. A name that is both a setting and a field is the
setting when its value is a `str`.

**An enum is its subcommands.** Each variant is a subcommand named by the
variant in kebab case; its payload is that subcommand's command, and a
payload that is itself such an enum nests. A variant without a payload is a
subcommand without arguments, described by its `Spec`'s `help`; a payload's
own `about` describes it otherwise. Every such command gets `help [COMMAND]`
as its last subcommand, so `tool help build`, `tool -h build` and
`tool build -h` print the same help.

**Errors come from the types.** A refused command line names what was wrong
in the type's terms, then prints the help of the command the words
addressed:

```text
tool: invalid value `fast` for `--mode`: expected debug, release or small
tool: invalid value `4294967296` for `--jobs`: expected an integer from 0 to 4294967295
tool: required argument `INPUT` is missing
tool: unknown option `--bogus` for `tool build`
```

`parse<T>(env, a)` reads the process's arguments; help goes to standard
output and answers `Exit(status: 0)`, a refusal goes to standard error and
answers `Exit(status: 2)`. `outcome<T>(env, a, argv)` parses any word list and
answers `Res<T, Stop>`, where `Stop` is `Help(String)`, `Refused(Refusal)`
or `Failed(AllocError)`, for a program that prints these itself (`zen` does).
The allocator holds repeated values and help text; argv and option values
are borrowed.

`parse` is a compiler-provided door, like `to_json` and `env.args<T>()`: the
C backend writes each type's parser at the call, from the type's fields,
variants and table, into calls of the `Command` engine below.

## `std.cli.Command`: the engine underneath

`std.cli.Command<T>` is the engine `parse<T>` drives, and a program may build
one by hand. One declaration drives parsing, validation, usage errors and
help, so the accepted grammar and its help cannot drift apart.

`T` is the program's enum of argument ids, one enum per command. Parsing
reports each argument it found as a `Found<T>` carrying its id, so a program
folds the matches into its own options with an exhaustive `match`; nothing is
looked up by its spelling, and an id added to the enum but not handled is a
compile error.

```zen
Id = Verbose | Jobs | Mode | Input

cmd ::= command<Id>(a, "tool build", "Build one input");
verbose = cmd.flag(Id.Verbose, "--verbose", Spec(short: 'v', help: "Say more")).try();
cmd.option(Id.Jobs, "--jobs", Spec(value: "N", kind: Kind.Unsigned, default: "4", env: "TOOL_JOBS")).try();
mode = cmd.option(Id.Mode, "--mode", Spec(value: "MODE", choices: "debug|release")).try();
cmd.positional(Id.Input, "INPUT", Spec(required: true, help: "Input path")).try();
cmd.conflicts(verbose, mode).try();
cmd.note("Environment:\n  TOOL_HOME  Where the cache lives");

parsed = cmd.parse(env, env.argv, 1).try();
parsed.problem.match({
    Ok(usage) => { /* usage.message(a, cmd.name) and cmd.help() */ },
    None      => parsed.found.loop((f) {
        f.id.match({
            Verbose => { loud = true; },
            Jobs    => { jobs = f.text.parse_usize().value_or(4); },
            Mode    => { chosen = f.text; },
            Input   => { input = f.text; },
        });
    }),
});
```

`flag`, `option` and `positional` take the id, the spelling (or a positional's
help name) and a `Spec`, whose fields are all optional:

| `Spec` field | meaning |
|---|---|
| `help` | the help column |
| `short` | a one-letter spelling: `-v`, `-x value`, `-xvalue` |
| `value` | the value's name in help, `VALUE` by default |
| `kind` | `Text`, or `Unsigned`/`Signed`, checked as integers while parsing |
| `min`, `max` | the range an integer must lie in |
| `choices` | accepted values separated by `|` |
| `default` | the value when neither the command line nor `env` gives one |
| `env` | a variable consulted when the command line omits the argument |
| `required`, `many` | must appear; may repeat |
| `hidden` | accepted but left out of help |
| `trailing` | for a derived `Vec<str>` field: the words after `--` (`trailing_args()` by hand) |

Each declaration returns an `Arg` handle; `conflicts(a, b)` and `requires(a, b)`
relate two of them. Relations count only explicit values: a default satisfies
`required` but never triggers or satisfies a relation, while a value from the
environment counts as given. `parsed.has(arg)` and `parsed.text(arg)` read one
argument directly.

Long options accept `--name value` and `--name=value`. A word starting with
`-` is never taken as an option's value unless the option is numeric and the
word is a number. `--` ends option parsing; after `trailing_args()` the words
that follow it are left for the program from `Matches.rest`.

Subcommands are declared on the parent with `command(id, name, about)`. A
subcommand word ends the parent's arguments and is reported in
`Matches.picked`; the program then parses the rest with the subcommand's own
`Command`, starting at `Picked.next`. `tool -h build` sets `help` and still
picks `build`, so the program can print the subcommand's help.

`help()` renders the usage line, the commands, arguments and options in
aligned columns with defaults, choices and variables, then the `note` text.
Parse failures are `Usage` values with a `Problem`; `message(a, command)`
gives the terminal text, such as "unknown option `--bogus` for `zen run`".
Malformed declarations (an option not spelled `--name`, `-h` or `--help`
redeclared, a spelling declared twice, a default the argument would refuse, a
required positional after an optional one, subcommands beside positionals,
an argument related to itself) are reported through the same channel as
`Problem.Declaration(Fault)` before any word is read.

Short-flag clustering such as `-abc`, typo suggestions and shell completion
are not part of the library.
