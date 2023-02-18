std: import("std"),
build: std.build,
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

build:  build.Builder {
    body:  {
        // target platform options
        target: self.Target.standardTargetOptions()
        // relase, debug ...
        mode:   self.Mode.standardModeOptions()
        // 
        exe:    self.Exe.standardExeOptions()

        // add executables
        exe.addExecutable ( 
            name: String("main")
            path: Path(String("./src/main.zim"))            
        )

        runCmd: exe.run()
        If (self.args){
            body:  {
                runCmd.addArgs(self.args)
            }
        }
    }
}