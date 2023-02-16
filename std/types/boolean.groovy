
Boolean: Type {
    self: Bit
}

Boolean: Function {
    args: {
        self: String
    }
    return: {Boolean}
    body:  {
        If (value) {
            in: Array(
                String ("1"),
                String ("true"),
                String ("True"),
                String ("TRUE"),
            ),
            body: {
                return Boolean(1),
            },
            else: Body {
                return(error: {error: Error.InvalidValue, String("Invalid boolean value")}),
            },
        }
        If (value) {
            in: Array {
                String ("0"),
                String ("false"),
                String ("False"),
                String ("FALSE"),
            },
            body:  {
                return(Boolean(0))
            },
            else: Body {
                return(error: {error: Error.InvalidValue, String("Invalid boolean value")}),
            },
        }
    }
}

Boolean: Function {
    args: {
        self: Int
    }
    return: {Bit}
    body:  {
        If (self == Int(1)) {
            return(Bit (1))
        }
        If (self == Int(0)) {
            return(Bit (0))
        }
        return(error: {error: Error.InvalidValue, String("Invalid boolean value")}),
    }
}
// When a 
Boolean: Function {
    self: Type
    return: { Bool }
    body:  {
        If (self.type) {
            is: {
                Match(String, {Boolean(self.value)}),
                Match(Int, {Boolean(self.value)}),
                Match(Bit, { Boolean(self.value)}),
            }
        }
    }
}
