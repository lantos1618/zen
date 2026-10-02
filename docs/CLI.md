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

The modes, the toolchain fields of `build.zen` and build reuse are described
under "How the compiler gets built" in [DESIGN.md](DESIGN.md).

## `std.cli`: declarative command lines

`std.cli.Command<T>` is the library behind the `zen` command. One declaration
drives parsing, validation, usage errors and help, so the accepted grammar and
its help cannot drift apart.

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
| `choices` | accepted values separated by `|` |
| `default` | the value when neither the command line nor `env` gives one |
| `env` | a variable consulted when the command line omits the argument |
| `required`, `many` | must appear; may repeat |
| `hidden` | accepted but left out of help |

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
