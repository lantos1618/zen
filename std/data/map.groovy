std: std()
{
    Array,
    Boolean,
    Function,
    HashFunc,
    Int,
    String,
    Type,
    Void,
}: std.types

Map: Type {
    keys: Array {
        self: {Type}
    },
    values: Array {
        self: {Type}
    },
    ordered: Bool,
    hashFunc: HashFunc
}

Map: Function {
    args: {
        self: Type
    }
    return: Map {
        keys: Array {String},
        values: Array {Type},
        ordered: Bool,
        hashFunc: HashFunc
    }
    body: {
        fieldPairsLoop: Loop(self.fieldPairs) {
            return.keys.push(fieldPairsLoop.value.key)
            return.values.push(fieldPairsLoop.value.value)
        }
        return()
    }
}

// insert

// get

// hasKey
