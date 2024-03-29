


<!-- grammar for zen -->

# Zen

Todo:
- [x] tokenize
- [x] astGen
- [ ] ast -> llvm
- [ ] ast -> lsp
- [x] Highlighting
- [ ] LSP
- [ ] TreeSitter


Mantra
- You should be able to work out where things come from without a editior
- one way to do things unless there is a really good reason not.
- The language should get out of the way of the programmer.

Rules
- Enums are just Types with many definable fields but only one instanciated field.
- Everything is exported unless you use the private/secret keyword
- Everything is mutable unless you use the const keyword.
- Everything should be explicit except for when there is 
    - one argument that is other than ``self``
    - You are setting a value with a defined type
- Only first level declarations are exported
- Functions are essentially just types with a body that is run when called


Features
- spread operator 
```groovy
Person: {...Address, name: String, age: Int.I32}
```
- object destructuring 
```groovy
{myValue, myOtherValue} = myObject
```
- shorthand property assignments 
```groovy
name: String("John")
age: Int.I32(10)

person: Person {name, age}

``` 
- no tuples without keys, just return an anonymous type, this is to keep code clean.
- All functions return a ```Res``` or ```ResErr```
    - no red/blue code (async/await)
    - ResErr the error must be handled. As the default error body will exit with ```Error(ErrorNotCaptured, "Error not captured")```

Reserved words
- ```CompTime```  - used to define a type or function that is run at compile time
- ```Body```      - used to define a body of code, this will take any fields on the type and make them available in the body
- ```Mut```     - used to define a mutable field
- ```Private```   - used to define a private field, values marked as are only modifiable by the same scope
- ```Secret```    - used to define a secret field,  values marked as are only visible to the same scope
- ```Enum```      - used to define an enum


reserved symbols
- ```:```         - used to define a type or instanciate a variable
- ```{}```        - used to define a type or modify a type
- ```()```        - used to call a function or instanciate a type

Inbuilt operators
- logical operators     ```== != > < >= <= && ||```
- maths operators       ```+ - * / %```
- bitwise operators     ```& ^ ~ << >>```

<!-- 
    if ( ==(x, y, x) )
    if ( ||||(==(x, y), ==(x, z)) )
    if ( x < y < z )
    if ( and(eq(x, y), eq(x, z)) )
    if ( or(eq(x, y), eq(x, z)))
    
 -->


# Variable Declaration

Variable declaration
```groovy
myString:   Mut{String}           // variable declaration with type inference
myString:   Mut{String("hello \"zen\"\n")}   // variable declaration with type inference and initialization

my_int:     Int        // error int must be initialized with a value unless it is defined by a compTime literal/value
my_int:     Int(1)     // const variable declaration with type and initialization

// code blocks
myBlock: Fn {
    myString: myString.concat(String("World!")) // this modifies the myString variable in the outer scope as there is no variable shadowing
}

```

Variable destructuring
```groovy
myFunction: Fn { 
    // args...
    return: { myValue: String, myOtherValue: Int} 
    // body...
}
{myValue, myOtherValue}: myFunction()
```

# Types
## Types
```groovy

// Type: {
//     self: String,
//     fields: Map {key: String, value: Type }
// }

// type definition
PersonSecret: {
// PersonSecret: Secret{Type} { // make this only visable in this scope
    secret: Secret{String()}, // only visible in this scope
}
PersonPrivate: {
// PersonPrivate: Private{Type} { // make this only modifiable in this scope
    private: String(), // only modifiable in this scope
}


// can also be to mark functions and types private
Person: {
    name:   Pub{String},
    age:    Pub{Int},
    // extending types
    ...PersonSecret,
    ...PersonPrivate,
}


// only visible in this scope
setSecretValue: Secret{Fn} {
    args:   { self: Person, value: String},
    return: ResultWithError {self: Person, error: ErrorType},
    fn: {
        self.secret = value
    }
}

setPrivateValue: Fn {
    args: { self: Person, value: String},
    return: ResultWithError { self: Person, error: ErrorType},
    fn: {
        self.private = value
    }
}

myPerson: Person {
    name: "John",
    age: 21,
}

io.std.writeLine(myPerson)      // > "Person { name: "John", age: 21 }"
io.std.writeLine(myPerson.name) // > "John"
io.std.writeLine(myPerson.age)  // > 21
io.std.writeLine(myPerson.type) // > "Person"

```

## Enums 
```groovy

// Enum {
//     self: TypeDescription,
//     value: Type(self)
// }

Currency: Enum {
    GBP: "GBP",
    USD: "USD",
    EUR: "EUR",
}

Rgb: Enum {
    RED,   // > 0
    GREEN, // > 1
    BLUE,  // > 2
}

Literal: Enum {
    String: String,
    Float:  Float.f128,
    Int:    Int.i128,
}

// 
Token: Enum {
    NewLine:    Int.usize,
    WhiteSpace: Int.usize,
    Comment:    String,
    Identifier: String,
    Literals:   Literal,
}



// usage example
currency: Currency.GBP
color: Rgb.RED
color1: Rgb(0)           // > Rgb.RED
color2: Rgb.parse("RED") // > Rgb.RED
token: Token.Comment("This is a comment")

io.std.writeLine(currency)                        // > Currency.GBP
io.std.writeLine(String.parse(currency))          // > "GBP"

io.std.writeLine(color)                           // > Rgb.RED
io.std.writeLine(int(color))                      // > 0
io.std.writeLine(String.parse(color))             // > "RED", just converts the enum to a string


io.std.writeLine(token)                           // > Token.Comment
io.std.writeLine(token.value)                     // > "This is a comment"
io.std.writeLine(String(token.value.Type))        // String

```

## Functions
### function declaration
functions are types with a body call
```groovy
Function: {
    a:   Type,
    f:   Body,
    r: Res || ResErr
}
```

#### Function example

```groovy
greet: Fn {
    self: Person,
    a: {
        message:    String,
    },
    r: Res{String},
    f:   {
        r(String.fmt("\(message) \(self.name)"))
    },
}
```
### Results
```groovy

Res: {
    self:   Type,
    error:  ErrorType,
}

ResErr: Res {
    error:  ErrorType
}
```

### Errors 
```groovy
Error: {
    error:      Enum,
    message:    String,
    fn:         Body,
}

```


#### Error example
```groovy
MyErrEnum: Enum {
    InvalidName,
    InvalidAmount,
    InvalidCurrency,
}

MyError: Err {
    error: MyErrEnum
}

// is the same as this
// MyError: {
//     ...Error
//     error: MyErrorEnum
// }


MyResult: Res {String}                                   // you can attempt to define an un defined type with {}
MyRes: Res {
    self: String
}                             // same as above but more explicit
MyRes: ResErr {self: String, error: MyErr}    // if the underType has more then one undefined type you must specify what field you are defining the type of

myResult: MyRes("hello") {                               // initializing a variable then defining what to do if there is an error
    io.std.writeLine("error")                               // print the error
}                                                           // this works because we define a body which applies to the error.body

myResult: MyRe(self:"hello")                            // same as above but more explicit

```

### Conditionals

There is only an if statement but can handle match also
```groovy

if (someThing) { doSomething() }

if (someThing) { 
    is: { doSomething() }, 
    else: { doSomethingElse() 
} }

if (Enum{A, B} (A)) { 
    is: ((A, { doA() }), (B, { doB() })), 
    else: { doSomethingElse() 
} }

myIntOption: Some(Int.i32(1))

myInt: if (myInt) { 
    is: { myInt }, 
    else: { Int.i32(0) } 
}

myInt: if (myIntOption) { 
    Int.I32, { }
    None, { Int.I32(0) }
}

MyEnum: Enum {
    A: String,
    B: Int,
    C
}

myFunc: Fn {
    MyEnum.A("hello")
}

myValue: if (t: myFunc()) {
    is: (
        (MyEnum.A, {t}),
        (MyEnum.B, {t.to(String)}),
        (MyEnum.C, {"C"})
    ),
    else: {"default"}
}


```



more examples

```groovy

// if: Fn {
//     args: {
//         self: Function || Boolean,
//         is: Body,
//     },
//     fn: Body()
// }

// standard ifstatement
// this works because the first argument can be passed as () and then the "then" body can be assumed in the following brackets {}
if (Boolean.True) {
    io.std.writeLine("true")
}
// if: Fn {
//     args: {
//         self: Enum { Function, Boolean },
//         is: Body,
//         else: Body,
//     },
//     fn: Body()
// }

if (Boolean.True) {
    is: {io.std.writeLine("true")},
    else: {io.std.writeLine("false")},
}
// we need to define then and else as there are two def types

// match statements
value: String("hello")
if (value) {
    is: Array(
        Match("hello") { io.std.writeLine("hello") },
        Match("world") { io.std.writeLine("world") }
    )
    // will complain ifthere are cases that are not covered
    else: { io.std.writeLine("not hello or world") },
}

```

### Loops
```groovy
// Loop: {
//     condition: Function || Boolean,
//     return: LoodHandle,
//     fn: Body,
// }

// Loop: {
//     condition: Function || Boolean,
//     return: LoodHandle,
//     fn: Body,
// }

counter:    Int(0)
myLoop:     Loop(true) {
    if (counter > 10) {
        myLoop.break()
    }
    io.std.writeLine(String.format("counter: ${String(counter))}"))
    counter: counter + 1
}

// we can also use iterate over a Array
myStrings:  Array(String("hello"), String("world"))
myLoop2:    Loop(myStrings) {
    io.std.writeLine(myLoop2.value)
}
```


# Example Project
project structure
```
project
├── build.zen
├── packages.zen
├── src
│   ├── main.zen
```

packages.json
```json
{
    "packages": [
        {
            "name": "dockerApi",
            "github": {
                "owner": "lantos-ltgm",
                "url": "https://github.com/lantos-ltgm/zen-docker-api.git",
                "branch": "master",
                "commit": "a1b2c3d4e5f6"
            }
        }
    ]
}
```

build.zen
```groovy
std:        @std                  // import the std lib
Build:      std.build

// load External packages
packages: Array(
    Build.Package(
        name: String("std"),
        path: Path(String("./packages/std")),
    ),
    ...Build.Packages.fromJson(Path(String("./packages.json"))),
)

main: Buld.Build {
    procjectName:   "project",
    srcPath:        "src",

    // load localFiles
    // this will go through and add all the .zen files and folders in the src folder
    // src/utils/other.zen
    // std.localPackages.utils.other
    localPackages: build.loadLocalPackages(
        srcPath,
    )

    // add executable
    self.executables build.Executable(
            name: "main",
            src: "main.zen",
            packages,
            localPackages,
    ),
}
```


src/utils/other.zen
```groovy
std: @std // import the std lib
{
    Function,
    Loop
}: std.functions,

someUtil: Fn {
    args: {},
    fn: {
        io.std.writeLine("hello world")
    }
}
```

src/main.zen
```groovy   
// std
std: @std
{
    Function,
    Loop
}: std.functions,
// custom
{
    Docker
}:  std.packages.dockerApi,
someUtil: std.localPackages.utils.other.someUtil,


// only 1st level declarations are exported
main: Fn {
    args: {},
    return: String,
    fn: {
        docker: Docker()
        // body.defer: {
        body.defer.add({
            docker.close()
        })
        containers:     docker.listContainers()
        containersLoop: Loop(containers) {
            io.std.writeLine(containersLoop.value.name)
            io.std.writeLine(containersLoop.value.status)
        }
    },
}

```
