std: @std,
{
    Type,
    String,
    Int,
    Float,
    Bool,
    Array,
    Result,
    ResultWithError,
}: std.types,
{
    Function,
    Loop,
    If,
}: std.functions,

LoopHandle: Type {
    value: Type
},

Loop: Function {
    args: {
        self: LoopHandle
        then: Body
    }
    return: self.Type
    body: Body {
        {
            If (self()) {
                args.then()
                fn()
            }
            return()
        }
    }
}
// iteration
Loop: Function {
    args: {
        self: Array,
        i: Int,
        next: ResultWithError,
        then: Body,
        loopHandle: LoopHandle {
            value: self.Type
        },
    }
    return: args.loopHandle.Type,
    body: Function {
        {
            If (i < self.size()) {
                next: ResultWithError(self[i])
                body(next)
                i.increment()
            } else {
                next.error = "Out of bounds"
            }
        }
    }
}