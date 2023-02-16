imports: {
    std,
    {
        io,
        time,
    }: std,
    {
        Function,
        Loop,
    }: std.functions,
    {
        String,
        Int,
        Bool,
        Array,
    }: std.types,
},
Bechmark: Function {
    args: {
        self: Body
    }
    body: {
        start: time.now()
        self.evaluate()
        end: time.now()
        duration: time.subtract(Array(end, start))
        io.println { String.format {"Duration: ${duration.format(time.nanoseconds)}"} }
    }
}