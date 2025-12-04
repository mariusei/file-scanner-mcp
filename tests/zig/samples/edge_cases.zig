const std = @import("std");
const builtin = @import("builtin");

//! Module-level documentation
//! This module contains edge cases for testing

/// Generic container type
pub fn GenericList(comptime T: type) type {
    return struct {
        items: []T,
        allocator: std.mem.Allocator,

        const Self = @This();

        pub fn init(allocator: std.mem.Allocator) Self {
            return Self{
                .items = &.{},
                .allocator = allocator,
            };
        }

        pub fn deinit(self: *Self) void {
            self.allocator.free(self.items);
        }
    };
}

/// Tagged union with payload
pub const ParseResult = union(enum) {
    success: struct {
        value: i64,
        remainder: []const u8,
    },
    failure: struct {
        message: []const u8,
        position: usize,
    },
    incomplete,
};

/// Extern struct for C interop
pub const CStruct = extern struct {
    x: c_int,
    y: c_int,
    data: [*]u8,
};

/// Packed struct for binary protocols
pub const PackedHeader = packed struct {
    version: u4,
    flags: u4,
    length: u16,
    checksum: u32,
};

/// Error set
pub const FileError = error{
    NotFound,
    PermissionDenied,
    OutOfMemory,
};

/// Function with complex signature
pub fn processData(
    allocator: std.mem.Allocator,
    input: []const u8,
    options: struct {
        validate: bool = true,
        max_size: usize = 1024,
    },
) FileError![]u8 {
    _ = options;
    return allocator.dupe(u8, input);
}

/// Async function (if supported)
pub fn asyncOperation() void {
    // Placeholder for async operations
}

/// Extern function declaration
extern "c" fn printf(format: [*:0]const u8, ...) c_int;

/// Comptime function
pub fn comptimeHash(comptime str: []const u8) u32 {
    var hash: u32 = 0;
    for (str) |c| {
        hash = hash *% 31 +% c;
    }
    return hash;
}

/// Nested struct with methods
pub const OuterStruct = struct {
    pub const InnerStruct = struct {
        value: i32,

        pub fn getValue(self: @This()) i32 {
            return self.value;
        }
    };

    inner: InnerStruct,

    pub fn getInnerValue(self: OuterStruct) i32 {
        return self.inner.getValue();
    }
};

test "generic list" {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    var list = GenericList(i32).init(allocator);
    defer list.deinit();
}

test "parse result" {
    const result: ParseResult = .incomplete;
    switch (result) {
        .success => {},
        .failure => {},
        .incomplete => {},
    }
}

test "comptime hash" {
    const hash = comptimeHash("hello");
    try std.testing.expect(hash != 0);
}
