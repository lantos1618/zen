std: @import("std"),
Http: std.http,
{
    Port
}: Http

Docker: Type {
    client: Http.HttpClient,
    host: String,
    port: Port,
}