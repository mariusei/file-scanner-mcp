const std = @import("std");

/// Configuration for the application
pub const Config = struct {
    name: []const u8,
    value: i32,

    /// Calculate the total value
    pub fn total(self: Config) i32 {
        return self.value * 2;
    }

    fn discard(self: Config) void {
        _ = self;
    }
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

    try stdout.print("Hello, {s}! {d}\n", .{ "World", clamp(helper(2, 3), 0, max_value) });
    try stdout.flush();
}

fn helper(x: i32, y: i32) i32 {
    return x + y;
}

pub inline fn fastAdd(a: u32, b: u32, c: u32) u32 {
    return a + b + c;
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

/// Liveness probe
pub fn isReady() bool {
    return max_value > 0;
}

/// Upper bound for clamped values
pub const max_value: i32 = 200;

/// Clamp a value into the inclusive range (private)
fn clamp(value: i32, lower: i32, upper: i32) i32 {
    if (value < lower) return lower;
    if (value > upper) return upper;
    return value;
}
