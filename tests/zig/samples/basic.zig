const std = @import("std");

/// Configuration for the application
pub const Config = struct {
    name: []const u8,
    value: i32,

    /// Calculate the total value
    pub fn total(self: Config) i32 {
        return self.value * 2;
    }

    fn private_helper(self: Config) void {
        _ = self;
    }
};

/// Status enumeration
pub const Status = enum {
    pending,
    running,
    completed,
    failed,
};

const Result = union(enum) {
    ok: i32,
    err: []const u8,
};

/// Main entry point for the application
pub fn main() !void {
    var stdout_buffer: [4096]u8 = undefined;
    var stdout_writer = std.fs.File.stdout().writer(&stdout_buffer);
    const stdout = &stdout_writer.interface;

    try stdout.print("Hello, {s}!\n", .{"World"});
    try stdout.flush();
}

fn helper(x: i32, y: i32) i32 {
    return x + y;
}

pub inline fn fastAdd(a: u32, b: u32) u32 {
    return a + b;
}

export fn c_api_function(ptr: [*]u8, len: usize) void {
    _ = ptr;
    _ = len;
}

test "basic test" {
    try std.testing.expect(true);
}

test "addition works" {
    const result = helper(2, 3);
    try std.testing.expectEqual(result, 5);
}
